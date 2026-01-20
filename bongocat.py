
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
import threading
from PyQt6.QtWidgets import QApplication, QLabel, QWidget, QMenu, QInputDialog
from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor, QTransform, QAction
from PyQt6.QtCore import Qt, QPoint, pyqtSignal, QObject, QTimer

__all__ = ()

class BongoCatWindow(QWidget):
    def __init__(self, neutral_pixmap, responses_pixmaps, scale, rotate, counter_pos):
        super().__init__()
        
        # Store original pixmaps for re-scaling/rotating in settings
        self.original_neutral = neutral_pixmap
        self.original_responses = responses_pixmaps

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
        
        # Initial values from command line (might be overridden by load_clicks)
        self.scale_factor = scale
        self.rotation = rotate
        self.counter_pos = counter_pos
        
        self.active_keys = set()
        self.active_mouse = set()
        self.kb_mapping = {}
        self.click_count = self.load_clicks()
        
        # Pre-process pixmaps with scale and rotation
        self.neutral = self.process_pixmap(self.original_neutral)
        self.responses = {name: self.process_pixmap(pm) for name, pm in self.original_responses.items()}
        
        # Pre-calculate max dimensions to avoid doing it in every layout update
        all_pixmaps = [self.neutral] + list(self.responses.values())
        self.max_w = max(p.width() for p in all_pixmaps if p)
        self.max_h = max(p.height() for p in all_pixmaps if p)
        self._current_ww, self._current_wh = 0, 0

        self.is_mirrored = False
        self.next_mirror_at = self.click_count + random.randint(5, 10)
        self.last_press_time = 0
        self.alternator = itertools.cycle([self.responses.get('r', self.neutral), self.responses.get('l', self.neutral)])
        
        self._stats_changed = False

        self.initUI()
        
    def init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS stats (id INTEGER PRIMARY KEY, clicks INTEGER)")
            
            # Update table if columns are missing (for existing users)
            for column, default in [("x", 100), ("y", 100), ("scale", 1.0), ("rotate", 0.0), ("pos", "'bottom'")]:
                try:
                    conn.execute(f"ALTER TABLE stats ADD COLUMN {column} {type(default).__name__} DEFAULT {default}")
                except sqlite3.OperationalError:
                    pass

            conn.execute("INSERT OR IGNORE INTO stats (id, clicks, x, y, scale, rotate, pos) VALUES (1, 0, 100, 100, 1.0, 0.0, 'bottom')")

    def load_clicks(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT clicks, x, y, scale, rotate, pos FROM stats WHERE id = 1")
                row = cursor.fetchone()
                if row:
                    self.saved_x = row[1]
                    self.saved_y = row[2]
                    # Apply DB values to the instance
                    self.scale_factor = row[3]
                    self.rotation = row[4]
                    self.counter_pos = row[5]
                    return row[0]
                return 0
        except:
            self.saved_x, self.saved_y = 100, 100
            return 0

    def save_stats(self, force=False):
        # Only save if forced (exit/settings) or if we really want periodic saves (disabled for now)
        if not force:
            return
            
        try:
            pos = self.pos()
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("UPDATE stats SET clicks = ?, x = ?, y = ?, scale = ?, rotate = ?, pos = ? WHERE id = 1", 
                             (self.click_count, pos.x(), pos.y(), float(self.scale_factor), float(self.rotation), str(self.counter_pos)))
                conn.commit()
            self._stats_changed = False
        except Exception as e:
            print(f"Error saving stats: {e}")

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
        # We use X11BypassWindowManagerHint again but only for Linux to allow off-screen movement
        # On Windows, FramelessWindowHint is usually enough.
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
        if os.name == 'posix':
            flags |= Qt.WindowType.X11BypassWindowManagerHint
            
        self.setWindowFlags(flags)
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
        
        # Determine if the cat is mostly upside down (rotation near 180 or -180)
        rot_norm = abs(self.rotation % 360)
        is_upside_down = rot_norm > 90 and rot_norm < 270

        # Adjust overlap based on position and rotation
        if self.counter_pos == 'top':
            overlap = int((90 if is_upside_down else 40) * self.scale_factor)
        else:
            overlap = int((40 if is_upside_down else 90) * self.scale_factor)
            
        wh = int(self.max_h + ch - overlap)
        
        # Only resize the window if dimensions actually changed to save CPU/lag on Windows
        buffer = 5
        if ww + buffer != self._current_ww or wh + buffer != self._current_wh:
            self._current_ww, self._current_wh = ww + buffer, wh + buffer
            self.setFixedSize(self._current_ww, self._current_wh)
        
        self.image_label.resize(int(iw), int(ih))
        
        if self.counter_pos == 'top':
            self.counter_label.move((ww - cw) // 2, 0)
            self.image_label.move((ww - iw) // 2, ch - overlap)
            self.counter_label.raise_()
        else:
            self.image_label.move((ww - iw) // 2, 0)
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
        
        settings_menu = menu.addMenu("Settings")
        
        scale_action = QAction("Scale", self)
        scale_action.triggered.connect(self.set_scale)
        settings_menu.addAction(scale_action)
        
        rotate_action = QAction("Rotate", self)
        rotate_action.triggered.connect(self.set_rotate)
        settings_menu.addAction(rotate_action)
        
        pos_action = QAction("Counter Position", self)
        pos_action.triggered.connect(self.set_counter_pos)
        settings_menu.addAction(pos_action)

        menu.addSeparator()
        
        fix_action = QAction("Fix device identification", self)
        fix_action.triggered.connect(self.fix_devices)
        
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(QApplication.instance().quit)
        
        menu.addAction(fix_action)
        menu.addSeparator()
        menu.addAction(exit_action)
        
        menu.exec(event.globalPos())

    def set_scale(self):
        val, ok = QInputDialog.getDouble(self, "Scale", "Factor (0.1 - 1.0):", self.scale_factor, 0.1, 1.0, 2, Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.X11BypassWindowManagerHint)
        if ok:
            self.scale_factor = val
            self.reinit_pixmaps()
            self.update_layout()
            self.update_display()
            self._stats_changed = True
            self.save_stats()

    def set_rotate(self):
        val, ok = QInputDialog.getInt(self, "Rotate", "Degrees (-360 - 360):", int(self.rotation), -360, 360, 1, Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.X11BypassWindowManagerHint)
        if ok:
            self.rotation = float(val)
            self.reinit_pixmaps()
            self.update_layout()
            self.update_display()
            self._stats_changed = True
            self.save_stats()

    def set_counter_pos(self):
        items = ["top", "bottom"]
        val, ok = QInputDialog.getItem(self, "Counter Position", "Select position:", items, items.index(self.counter_pos), False, Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.X11BypassWindowManagerHint)
        if ok:
            self.counter_pos = val.lower()
            self.update_layout()
            # Re-apply window flags and show to ensure mouse events are still captured
            self.show()
            self.update_display()
            self._stats_changed = True
            self.save_stats()

    def reinit_pixmaps(self):
        # We need to reload the original pixmaps to re-process them with new scale/rotate
        if hasattr(self, 'original_neutral'):
            self.neutral = self.process_pixmap(self.original_neutral)
            self.responses = {name: self.process_pixmap(pm) for name, pm in self.original_responses.items()}
            
            # Update max dimensions
            all_pixmaps = [self.neutral] + list(self.responses.values())
            self.max_w = max(p.width() for p in all_pixmaps if p)
            self.max_h = max(p.height() for p in all_pixmaps if p)

            # CRITICAL: Re-initialize the alternator with newly scaled pixmaps
            self.alternator = itertools.cycle([self.responses.get('r', self.neutral), self.responses.get('l', self.neutral)])
            
            # Update counter label style for new scale
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

    def fix_devices(self):
        if hasattr(self, 'rehook_callback'):
            self.rehook_callback()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            new_pos = event.globalPosition().toPoint() - self.drag_pos
            self.move(new_pos)
            self._stats_changed = True
            event.accept()

def load_assets(default, path):
    # Determine the base directory for assets
    # If running as a bundled executable (PyInstaller), use _MEIPASS
    if hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
    else:
        # On Linux, if installed system-wide, use /opt/bongocat
        # Otherwise, use current working directory
        if os.name == 'posix' and os.path.exists('/opt/bongocat') and not os.path.exists(os.path.join(os.getcwd(), path)):
            base_path = '/opt/bongocat'
        else:
            base_path = os.getcwd()

    directory = os.path.join(base_path, path)
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
    # Suppress scary OSError [Errno 19] when devices are disconnected
    # We monkey-patch the thread exception handler
    def handle_thread_exception(args):
        if isinstance(args.exc_value, OSError) and args.exc_value.errno == 19:
            print("Device disconnected.")
        else:
            # Default behavior for other exceptions
            sys.__excepthook__(args.exc_type, args.exc_value, args.exc_traceback)

    threading.excepthook = handle_thread_exception

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
    
    # Initialize window with CLI args first
    window = BongoCatWindow(neutral, responses, scale, rotate, counter_pos)
    
    # Now, if CLI args were NOT provided (i.e. they are at their default values),
    # we attempt to load saved settings from the DB.
    try:
        with sqlite3.connect(window.db_path) as conn:
            cursor = conn.execute("SELECT scale, rotate, pos FROM stats WHERE id = 1")
            row = cursor.fetchone()
            if row:
                # Check if each argument was actually provided by the user
                # docopt.docopt() returns the default string from __doc__ if the arg is missing.
                if arguments['--scale'] is None: 
                    window.scale_factor = float(row[0])
                if arguments['--rotate'] is None: 
                    window.rotation = float(row[1])
                if arguments['--counter-position'] is None: 
                    window.counter_pos = str(row[2])
                
                # Force re-processing if we loaded anything from DB
                window.reinit_pixmaps()
                window.update_layout()
    except Exception as e:
        print(f"Debug: DB load error: {e}")

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
        # Optimization: return immediately if not a button event to avoid lag on Windows
        if not isinstance(event, mouse.ButtonEvent):
            return
            
        if event.event_type == 'down':
            event_queue.put(('mouse_down', event.button))
        else:
            event_queue.put(('mouse_up', event.button))

    def rehook():
        # Use exec to restart the process and re-identify devices from scratch
        # This is the most reliable way as it clears all library internal states and file descriptors
        print("Restarting Bongo Cat to re-identify devices...")
        try:
            window.save_stats(force=True)
            # On Windows, os.execv doesn't work the same way as on Unix.
            # We use subprocess to start a new process and exit the current one.
            if os.name == 'nt':
                import subprocess
                subprocess.Popen([sys.executable] + sys.argv)
                app.quit()
            else:
                os.execv(sys.executable, [sys.executable] + sys.argv)
        except Exception as e:
            print(f"Error restarting: {e}")

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
                        window._stats_changed = True
                
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
        elif any_up or (current_time - window.last_press_time > (0 if os.name == 'nt' else 0.05)):
            window.update_display()

    def watchdog():
        if window.active_keys:
            # Filter out unknown keys and handle potential library errors
            valid_keys = set()
            for k in window.active_keys:
                try:
                    if k != 'unknown' and keyboard.is_pressed(k):
                        valid_keys.add(k)
                except:
                    pass
            window.active_keys = valid_keys
            window.update_display()

    timer = QTimer()
    timer.timeout.connect(process_queue)
    # Increase frequency on Windows to process events faster
    timer.start(1 if os.name == 'nt' else 10)

    wd_timer = QTimer()
    wd_timer.timeout.connect(watchdog)
    wd_timer.start(1000)

    keyboard.hook(on_key)
    mouse.hook(on_mouse)
    sys.exit(app.exec())

if __name__ == '__main__':
    start()
