# Bongo Cat Overlay

Bongo Cat overlay for streamers or just for fun. It tracks your keyboard and mouse activity and displays an animated cat on your screen.
<br>
![Bongo Cat](./images/kb-mouse/idle.png)

## Features

- Tracks keyboard and mouse clicks.
- Counter for total clicks (saved in a local database).
- Supports scaling and rotation.
- Interactive window (can be moved by dragging).
- Mirrored mode activation after a certain number of clicks.

## Installation

To install Bongo Cat and set it up as a system-wide command, follow these steps:

1. **Quick Install (curl | bash):**

   ```bash
   curl -sSL https://raw.githubusercontent.com/queendekim/bongocat/master/install.sh | bash
   ```

   **Or install manually:**

   ```bash
   git clone https://github.com/queendekim/bongocat
   cd bongocat
   chmod +x install.sh
   ./install.sh
   ```

2. **Environment Path:**
   The script installs the `bongocat` command to `~/.local/bin`. Make sure this directory is in your `PATH`. If not, add the following line to your `.bashrc` or `.zshrc`:

   ```bash
   export PATH="$HOME/.local/bin:$PATH"
   ```

## Usage

Run the overlay using the command:

```bash
bongocat
```

*Note: On Linux, Bongo Cat requires root privileges to capture keyboard and mouse events. The command will automatically prompt for `sudo` if needed.*

### Options

- `--scale=<n>`: Scale factor (0-1) [default: 1.0]
- `--rotate=<deg>`: Rotation in degrees (-360 to 360) [default: 0]

Example:
```bash
bongocat --scale=0.8 --rotate=15
```

### Controls

- **Drag with Mouse**: Move the window around your screen.
- **Shift + F4**: Close the application.

## Customization

You can customize the images by modifying the files in `images/kb-mouse/`. 
- `idle.png`: The neutral state.
- `l.png` and `r.png`: The states for left and right paw actions.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Additional information

This project is based on the [Exahilosys/bongocat](https://github.com/Exahilosys/bongocat) repository.
