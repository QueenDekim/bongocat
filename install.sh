#!/bin/bash

# Bongo Cat Installation Script
# This script installs Bongo Cat and its dependencies, then creates a system-wide command.

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

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

# 2. Define installation directory
INSTALL_DIR="$HOME/.local/share/bongocat"

# 3. Clone or update the repository
if [ -d "$INSTALL_DIR" ]; then
    echo -e "${BLUE}Updating existing installation in $INSTALL_DIR...${NC}"
    cd "$INSTALL_DIR"
    git pull
else
    echo -e "${BLUE}Cloning repository to $INSTALL_DIR...${NC}"
    git clone https://github.com/queendekim/bongocat "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# 4. Create virtual environment and install dependencies
echo -e "${BLUE}Setting up virtual environment and installing dependencies...${NC}"
python3 -m venv .venv
source .venv/bin/activate

# Install required packages
# Note: PyQt6 is used in the code but not in install_requires in setup.py, adding it here.
pip install --upgrade pip
pip install -r requirements.txt

# 5. Create the launcher script
echo -e "${BLUE}Creating launcher script and setting permissions...${NC}"
BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"

# Configure python to have permissions to read raw input without global sudo
# We use setcap to allow the venv python to access input devices
echo -e "${BLUE}Requesting sudo to set capabilities for the virtual environment...${NC}"
sudo setcap 'cap_dac_override,cap_sys_rawio,cap_net_raw+ep' "$INSTALL_DIR/.venv/bin/python3"

cat << EOF > "$BIN_DIR/bongocat"
#!/bin/bash
# Run bongo cat from its installation directory so it can find assets
cd "$INSTALL_DIR"
# Use the venv python directly (it has the capabilities set)
"$INSTALL_DIR/.venv/bin/python3" "$INSTALL_DIR/bongocat.py" "\$@"
EOF

chmod +x "$BIN_DIR/bongocat"

# 6. Final instructions
echo -e "${GREEN}Installation complete!${NC}"
echo -e "You can now run Bongo Cat using the command: ${BLUE}bongocat${NC}"

# Check if BIN_DIR is in PATH
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo -e "${RED}Warning: $BIN_DIR is not in your PATH.${NC}"
    echo -e "Add this line to your .bashrc or .zshrc:"
    echo -e "${BLUE}export PATH=\"\$HOME/.local/bin:\$PATH\"${NC}"
fi
"
