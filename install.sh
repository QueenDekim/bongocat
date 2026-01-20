#!/bin/bash

# Bongo Cat Installation/Uninstallation Script

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Detect real user when run with sudo
REAL_USER=${SUDO_USER:-$USER}
REAL_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)

INSTALL_DIR="$REAL_HOME/.local/share/bongocat"
BIN_DIR="$REAL_HOME/.local/bin"

# Function to uninstall
uninstall() {
    echo -e "${BLUE}Uninstalling Bongo Cat for user $REAL_USER...${NC}"
    
    if [ -f "$BIN_DIR/bongocat" ]; then
        rm "$BIN_DIR/bongocat"
        echo -e "${GREEN}Removed launcher script.${NC}"
    fi
    
    if [ -d "$INSTALL_DIR" ]; then
        rm -rf "$INSTALL_DIR"
        echo -e "${GREEN}Removed installation directory.${NC}"
    fi
    
    echo -e "${GREEN}Uninstallation complete!${NC}"
    exit 0
}

# Check for arguments
while getopts "u" opt; do
  case $opt in
    u)
      uninstall
      ;;
    \?)
      echo "Usage: $0 [-u]"
      exit 1
      ;;
  esac
done

echo -e "${BLUE}Starting Bongo Cat installation for user $REAL_USER...${NC}"

# 1. Check for Python and Git
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: python3 is not installed.${NC}"
    exit 1
fi

if ! command -v git &> /dev/null; then
    echo -e "${RED}Error: git is not installed.${NC}"
    exit 1
fi

# 2. Clone or update the repository
if [ -d "$INSTALL_DIR" ]; then
    echo -e "${BLUE}Updating existing installation in $INSTALL_DIR...${NC}"
    cd "$INSTALL_DIR"
    sudo -u "$REAL_USER" git pull
else
    echo -e "${BLUE}Cloning repository to $INSTALL_DIR...${NC}"
    mkdir -p "$(dirname "$INSTALL_DIR")"
    chown "$REAL_USER:$REAL_USER" "$(dirname "$INSTALL_DIR")" || true
    sudo -u "$REAL_USER" git clone https://github.com/queendekim/bongocat "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# 3. Create virtual environment and install dependencies
echo -e "${BLUE}Setting up virtual environment and installing dependencies...${NC}"
sudo -u "$REAL_USER" python3 -m venv .venv
source .venv/bin/activate

# Install required packages as real user to avoid permission issues in cache
sudo -u "$REAL_USER" "$INSTALL_DIR/.venv/bin/pip" install --upgrade pip
sudo -u "$REAL_USER" "$INSTALL_DIR/.venv/bin/pip" install -r requirements.txt

# 4. Create the launcher script
echo -e "${BLUE}Creating launcher script and setting permissions...${NC}"
sudo -u "$REAL_USER" mkdir -p "$BIN_DIR"

# Check if user is in 'input' group for raw access
if ! groups "$REAL_USER" | grep &>/dev/null "\binput\b"; then
    echo -e "${BLUE}Adding user $REAL_USER to 'input' group...${NC}"
    usermod -aG input "$REAL_USER"
fi

# Ensure udev rules exist for the input group
echo -e "${BLUE}Setting up udev rules for input devices...${NC}"
cat << EOF | sudo tee /etc/udev/rules.d/99-input.rules > /dev/null
KERNEL=="event*", NAME="input/%k", MODE="0660", GROUP="input"
EOF
sudo udevadm control --reload-rules && sudo udevadm trigger

echo -e "${RED}Note: You MUST logout and login again (or restart) for group changes and udev rules to take effect.${NC}"

cat << EOF > "$BIN_DIR/bongocat"
#!/bin/bash
# Run bongo cat from its installation directory so it can find assets
cd "$INSTALL_DIR"

# Check if we have permissions to read input devices
if [ -r /dev/input/event0 ] || [ "\$EUID" -eq 0 ] || groups | grep &>/dev/null "\binput\b"; then
  "$INSTALL_DIR/.venv/bin/python3" "$INSTALL_DIR/bongocat.py" "\$@"
else
  # If not, fallback to sudo
  echo "Bongo Cat requires access to input devices. Running with sudo..."
  sudo "$INSTALL_DIR/.venv/bin/python3" "$INSTALL_DIR/bongocat.py" "\$@"
fi
EOF

chown "$REAL_USER:$REAL_USER" "$BIN_DIR/bongocat"
chmod +x "$BIN_DIR/bongocat"

# 5. Final instructions
echo -e "${GREEN}Installation complete!${NC}"
echo -e "You can now run Bongo Cat using the command: ${BLUE}bongocat${NC}"

# Check if BIN_DIR is in PATH (checking both current and real user's PATH)
# We try to get the PATH from the user's preferred shell to be more accurate
USER_PATH=$(sudo -u "$REAL_USER" printenv PATH)
# We use -i (interactive) and -l (login) to ensure we get the same PATH as the user's terminal
SHELL_PATH=$(sudo -u "$REAL_USER" -i ${SHELL:-sh} -c 'echo $PATH' 2>/dev/null || echo "")

# Debug info
# echo -e "${BLUE}Debug: BIN_DIR=$BIN_DIR${NC}"
# echo -e "${BLUE}Debug: Current PATH=$PATH${NC}"
# echo -e "${BLUE}Debug: USER_PATH=$USER_PATH${NC}"
# echo -e "${BLUE}Debug: SHELL_PATH=$SHELL_PATH${NC}"

if [[ ":$PATH:" != *":$BIN_DIR:"* ]] && [[ ":$USER_PATH:" != *":$BIN_DIR:"* ]] && [[ ":$SHELL_PATH:" != *":$BIN_DIR:"* ]]; then
    echo -e "${RED}Warning: $BIN_DIR is not in your PATH.${NC}"
    echo -e "Add this line to your .bashrc or .zshrc:"
    echo -e "${BLUE}export PATH=\"\$HOME/.local/bin:\$PATH\"${NC}"
fi
