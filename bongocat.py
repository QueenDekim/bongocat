
"""Bongo Cat Overlay

Usage:
    bongocat.py [options]
    bongocat.py -h | --help

Options:
    -h --help                    Show this screen
    -s --scale=<n>               Scale factor (0-1) [default: 1.0]
    -r --rotate=<deg>            Rotation in degrees (-360 to 360) [default: 0]
    -p --counter-position=<pos>  Position of the counter (top|bottom) [default: bottom]
"""

import sys, os

# Suppress Qt DBus warnings when running as root/sudo
os.environ["QT_LOGGING_RULES"] = "qt.qpa.theme.dbus=false;qt.qpa.theme.gnome=false"

import itertools
import random
import queue
import time
import sqlite3
from PyQt6.QtWidgets import QApplication, QLabel, QWidget, QMenu
from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor, QTransform, QAction
from PyQt6.QtCore import Qt, QPoint, pyqtSignal, QObject, QTimer

__all__ = ()

class BongoCatWindow(QWidget):
    def __init__(self, neutral_pixmap, responses_pixmaps, scale, rotate, counter_pos):
        super().__init__()
        
        # Determine the database path, respecting the real user if running with sudo
        home = os.path.expanduser("~")
        if os.environ.get("SUDO_USER") and os.name == 'posix':
            try:
                import pwd
                home = pwd.getpwnam(os.environ.get("SUDO_USER")).pw_dir
            except (ImportError, KeyError):
                pass
        
        self.db_path = os.path.join(home, ".bongocat_stats.db")
        self.init_db()
        self.scale_factor = scale
        self.rotation = rotate
        self.counter_pos = counter_pos
        
        # Pre-process pixmaps with scale and rotation
        self.neutral = self.process_pixmap(neutral_pixmap)
        self.responses = {name: self.process_pixmap(pm) for name, pm in responses_pixmaps.items()}
        
        self.active_keys = set()
        self.active_mouse = set()
        self.kb_mapping = {}
        self.click_count = self.load_clicks()
        self.is_mirrored = False
        self.next_mirror_at = self.click_count + random.randint(5, 10)
        self.last_press_time = 0
        self.alternator = itertools.cycle([self.responses.get('r', self.neutral), self.responses.get('l', self.neutral)])
        
        self.initUI()
        
    def init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS stats (id INTEGER PRIMARY KEY, clicks INTEGER)")
            
            # Update table if columns are missing (for existing users)
            try:
                conn.execute("ALTER TABLE stats ADD COLUMN x INTEGER DEFAULT 100")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE stats ADD COLUMN y INTEGER DEFAULT 100")
            except sqlite3.OperationalError:
                pass

            conn.execute("INSERT OR IGNORE INTO stats (id, clicks, x, y) VALUES (1, 0, 100, 100)")

    def load_clicks(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT clicks, x, y FROM stats WHERE id = 1")
                row = cursor.fetchone()
                if row:
                    self.saved_x = row[1]
                    self.saved_y = row[2]
                    return row[0]
                return 0
        except:
            self.saved_x, self.saved_y = 100, 100
            return 0

    def save_stats(self):
        try:
            pos = self.pos()
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("UPDATE stats SET clicks = ?, x = ?, y = ? WHERE id = 1", 
                             (self.click_count, pos.x(), pos.y()))
        except:
            pass

    def process_pixmap(self, pixmap):
        if pixmap is None:
            return None
            
        transform = QTransform()
        if self.scale_factor > 1.0:
            print(f"The scale cannot be greater than 1 (you specified a scale of {self.scale_factor})")
            print("set to 1")
            self.scale_factor = 1.0
        if self.scale_factor < 0:
            print(f"The scale cannot be less than 0 (you specified a scale of {self.scale_factor})")
            print("set to 0")
            self.scale_factor = 0

        if self.scale_factor != 1.0:
            transform.scale(self.scale_factor, self.scale_factor)
        if self.rotation != 0:
            transform.rotate(self.rotation)
            
        return pixmap.transformed(transform, Qt.TransformationMode.SmoothTransformation)

    def initUI(self):
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool | Qt.WindowType.X11BypassWindowManagerHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.image_label = QLabel(self)
        self.image_label.setPixmap(self.neutral)
        
        self.counter_label = QLabel(str(self.click_count), self)
        self.counter_label.setStyleSheet(f"""
            color: #333333; 
            font-family: Helvetica; 
            font-size: {int(40 * self.scale_factor)}pt; 
            font-weight: bold; 
            padding: 1px 3px;
            background-color: white;
            border: 2px solid #333333;
            border-radius: 5%;
        """)
        self.counter_label.adjustSize()
            
        all_pixmaps = [self.neutral] + list(self.responses.values())
        self.max_w = max(p.width() for p in all_pixmaps if p)
        self.max_h = max(p.height() for p in all_pixmaps if p)
        
        self.update_layout()
        if hasattr(self, 'saved_x'):
            self.move(self.saved_x, self.saved_y)
        self.show()

    def update_layout(self):
        img = self.image_label.pixmap()
        iw = img.width()
        ih = img.height()
        
        self.counter_label.adjustSize()
        cw = self.counter_label.width()
        ch = self.counter_label.height()
        
        ww = int(max(self.max_w, cw))
        overlap = int(90 * self.scale_factor)
        wh = int(self.max_h + ch - overlap)        
        self.setFixedSize(ww, wh)
        
        self.image_label.resize(int(iw), int(ih))
        
        if self.counter_pos == 'top':
            self.counter_label.move((ww - cw) // 2, 0)
            self.image_label.move(0, ch - overlap)
        else:
            self.image_label.move(0, 0)
            self.counter_label.move((ww - cw) // 2, self.max_h - overlap)
            
        self.image_label.raise_()
            
    def update_display(self):
        img = self.neutral
        
        if self.active_mouse:
            if 'left' in self.active_mouse:
                img = self.responses.get('l', self.neutral)
            elif 'right' in self.active_mouse:
                img = self.responses.get('r', self.neutral)
        elif self.active_keys:
            last_key = list(self.active_keys)[-1]
            img = self.kb_mapping.get(last_key, self.neutral)
            
        if self.click_count >= self.next_mirror_at:
            self.is_mirrored = not self.is_mirrored
            self.next_mirror_at = self.click_count + random.randint(5, 10)

        if self.is_mirrored:
            mirrored_image = img.toImage().mirrored(True, False)
            img = QPixmap.fromImage(mirrored_image)

        self.image_label.setPixmap(img)
        self.counter_label.setText(str(self.click_count))
        self.update_layout()
            
    def contextMenuEvent(self, event):
        menu = QMenu(self)
        
        fix_action = QAction("Fix device identification", self)
        fix_action.triggered.connect(self.fix_devices)
        
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(QApplication.instance().quit)
        
        menu.addAction(fix_action)
        menu.addSeparator()
        menu.addAction(exit_action)
        
        menu.exec(event.globalPos())

    def fix_devices(self):
        import keyboard
        import mouse
        try:
            keyboard.unhook_all()
            mouse.unhook_all()
            # The hooks will be re-established in the start() function's context if we use a signal
            # but since we are in a different scope, we'll emit a custom signal or just call the hooks again.
            # However, start() is not a class, so let's use a simpler approach: 
            # keyboard.hook and mouse.hook are global in the library.
            # We need to pass the callback functions here.
            if hasattr(self, 'rehook_callback'):
                self.rehook_callback()
        except Exception as e:
            print(f"Error re-hooking devices: {e}")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_pos)
            self.save_stats()
            event.accept()

def load_assets(default, path):
    directory = os.path.join(os.getcwd(), path)
    responses = {}
    neutral = None
    extensions = ('.png', '.jpg', '.jpeg')
    
    if not os.path.exists(directory):
        raise FileNotFoundError(f"Assets directory not found: {directory}")

    for entry in os.scandir(directory):
        if not entry.is_file():
            continue
        name, ext = os.path.splitext(entry.name)
        if ext.lower() not in extensions:
            continue
        pixmap = QPixmap(entry.path)
        if name.lower() == default.lower():
            neutral = pixmap
        else:
            responses[name.lower()] = pixmap
            
    if neutral is None:
        raise ValueError(f"Missing file '{default}' for neutral state in {directory}.")
    return neutral, responses

def start():
    import docopt
    
    # Check for root privileges on Linux as it's required for keyboard/mouse hooking
    if os.name == 'posix' and os.geteuid() != 0:
        print("Error: Bongo Cat requires root privileges to capture keyboard and mouse events on Linux.")
        print("Please run it with sudo:")
        print(f"    sudo {sys.argv[0]} {' '.join(sys.argv[1:])}")
        sys.exit(1)

    import keyboard
    import mouse

    arguments = docopt.docopt(__doc__)
    app = QApplication(sys.argv)
    
    default = 'idle'
    path = 'images/kb-mouse'
    
    try:
        scale = float(arguments['--scale'] or 1.0)
    except (ValueError, TypeError):
        print(f"Warning: Invalid scale value '{arguments['--scale']}'. Using default: 1.0")
        scale = 1.0

    try:
        rotate = float(arguments['--rotate'] or 0.0)
    except (ValueError, TypeError):
        print(f"Warning: Invalid rotate value '{arguments['--rotate']}'. Using default: 0")
        rotate = 0.0

    counter_pos = (arguments['--counter-position'] or 'bottom').lower()
    if counter_pos not in ['top', 'bottom']:
        print(f"Warning: Invalid counter position '{counter_pos}'. Using default: bottom")
        counter_pos = 'bottom'
    
    neutral, responses = load_assets(default, path)
    window = BongoCatWindow(neutral, responses, scale, rotate, counter_pos)
    event_queue = queue.Queue()

    def on_key(event):
        try:
            if event.name == 'f4' and keyboard.is_pressed('shift'):
                QTimer.singleShot(0, app.quit)
                return
            if event.event_type == 'down':
                event_queue.put(('key_down', event.name))
            else:
                event_queue.put(('key_up', event.name))
        except:
            pass

    def on_mouse(event):
        if isinstance(event, mouse.ButtonEvent):
            if event.event_type == 'down':
                event_queue.put(('mouse_down', event.button))
            else:
                event_queue.put(('mouse_up', event.button))

    def rehook():
        keyboard.unhook_all()
        mouse.unhook_all()
        keyboard.hook(on_key)
        mouse.hook(on_mouse)
        print("Devices re-identified.")

    window.rehook_callback = rehook
    
    def process_queue():
        current_time = time.time()
        any_down = False
        any_up = False

        while True:
            try:
                etype, data = event_queue.get_nowait()
                if etype in ('key_down', 'mouse_down'):
                    if etype == 'key_down':
                        if data not in window.active_keys:
                            window.active_keys.add(data)
                            window.kb_mapping[data] = next(window.alternator)
                            any_down = True
                    else:
                        if data not in window.active_mouse:
                            window.active_mouse.add(data)
                            any_down = True
                    
                    if any_down:
                        window.click_count += 1
                        window.save_stats()
                
                elif etype == 'key_up':
                    window.active_keys.discard(data)
                    any_up = True
                elif etype == 'mouse_up':
                    window.active_mouse.discard(data)
                    any_up = True
            except queue.Empty:
                break

        if any_down:
            window.last_press_time = current_time
            window.update_display()
        elif any_up or (current_time - window.last_press_time > 0.05):
            window.update_display()

    def watchdog():
        if window.active_keys:
            window.active_keys = {k for k in window.active_keys if keyboard.is_pressed(k)}
            window.update_display()

    timer = QTimer()
    timer.timeout.connect(process_queue)
    timer.start(10)

    wd_timer = QTimer()
    wd_timer.timeout.connect(watchdog)
    wd_timer.start(1000)

    keyboard.hook(on_key)
    mouse.hook(on_mouse)
    sys.exit(app.exec())

if __name__ == '__main__':
    start()
