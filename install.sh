#!/bin/bash

# Bongo Cat Installation/Uninstallation Script

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

INSTALL_DIR="$HOME/.local/share/bongocat"
BIN_DIR="$HOME/.local/bin"

# Function to uninstall
uninstall() {
    echo -e "${BLUE}Uninstalling Bongo Cat...${NC}"
    
    if [ -f "$BIN_DIR/bongocat" ]; then
        rm "$BIN_DIR/bongocat"
        echo -e "${GREEN}Removed launcher script.${NC}"
    fi
    
    if [ -d "$INSTALL_DIR" ]; then
        # We need sudo to remove the root-owned python binary in venv
        echo -e "${BLUE}Requesting sudo to remove installation files...${NC}"
        sudo rm -rf "$INSTALL_DIR"
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

echo -e "${BLUE}Starting Bongo Cat installation...${NC}"

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
    git pull
else
    echo -e "${BLUE}Cloning repository to $INSTALL_DIR...${NC}"
    git clone https://github.com/queendekim/bongocat "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# 3. Create virtual environment and install dependencies
echo -e "${BLUE}Setting up virtual environment and installing dependencies...${NC}"
python3 -m venv .venv
source .venv/bin/activate

# Install required packages
pip install --upgrade pip
pip install -r requirements.txt

# 4. Create the launcher script
echo -e "${BLUE}Creating launcher script and setting permissions...${NC}"
mkdir -p "$BIN_DIR"

# Configure python to have permissions to read raw input without global sudo
echo -e "${BLUE}Requesting sudo to set permissions for the virtual environment...${NC}"
# We need to resolve the symlink because setuid doesn't work on symlinks
REAL_PYTHON=$(readlink -f "$INSTALL_DIR/.venv/bin/python3")
# Set ownership to root and add setuid bit
sudo chown root:root "$REAL_PYTHON"
sudo chmod +s "$REAL_PYTHON"

cat << EOF > "$BIN_DIR/bongocat"
#!/bin/bash
# Run bongo cat from its installation directory so it can find assets
cd "$INSTALL_DIR"
# The python executable has setuid bit, so it runs as root even when called by user
"$INSTALL_DIR/.venv/bin/python3" "$INSTALL_DIR/bongocat.py" "\$@"
EOF

chmod +x "$BIN_DIR/bongocat"

# 5. Final instructions
echo -e "${GREEN}Installation complete!${NC}"
echo -e "You can now run Bongo Cat using the command: ${BLUE}bongocat${NC}"

# Check if BIN_DIR is in PATH
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo -e "${RED}Warning: $BIN_DIR is not in your PATH.${NC}"
    echo -e "Add this line to your .bashrc or .zshrc:"
    echo -e "${BLUE}export PATH=\"\$HOME/.local/bin:\$PATH\"${NC}"
fi

