> **Note:** If you need PDF report export (`WeasyPrint`), install the OS-level graphics/text dependencies below. If you do not need server-side PDF export, you can skip these steps without affecting the rest of Trend Pulse.

<details>
<summary><b>Windows Installation Steps</b></summary>

```powershell
# 1. Download and install GTK3 Runtime (execute on the host machine)
# URL: https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases
# Download and install the latest .exe release using the default path when possible.

# 2. Add the GTK bin directory to PATH (open a new terminal afterwards)
set PATH=C:\Program Files\GTK3-Runtime Win64\bin;%PATH%

# Optional: persist in user PATH
setx PATH "C:\Program Files\GTK3-Runtime Win64\bin;%PATH%"

# If installed in a custom location, replace the path above or set GTK_BIN_PATH=<your-bin-path>

# 3. Verify installation in a new terminal
python -m ReportEngine.utils.dependency_check
# Expected output includes "✓ Pango dependency check passed"
```

</details>

<details>
<summary><b>macOS Installation Steps</b></summary>

```bash
# 1. Install system dependencies
brew install pango gdk-pixbuf libffi

# 2. Export library path (required)
# Apple Silicon:
export DYLD_LIBRARY_PATH=/opt/homebrew/lib:$DYLD_LIBRARY_PATH
# Intel Mac:
# export DYLD_LIBRARY_PATH=/usr/local/lib:$DYLD_LIBRARY_PATH

# Recommended: persist in ~/.zshrc
echo 'export DYLD_LIBRARY_PATH=/opt/homebrew/lib:$DYLD_LIBRARY_PATH' >> ~/.zshrc
source ~/.zshrc

# 3. Verify in a new terminal
python -m ReportEngine.utils.dependency_check
```

**Troubleshooting:**
- Make sure you reloaded `~/.zshrc` (`source ~/.zshrc`) and opened a new terminal session.
- Confirm with `echo $DYLD_LIBRARY_PATH`.

</details>

<details>
<summary><b>Ubuntu / Debian Installation Steps</b></summary>

```bash
sudo apt-get update
sudo apt-get install -y \
  libpango-1.0-0 \
  libpangoft2-1.0-0 \
  libffi-dev \
  libcairo2

if sudo apt-cache show libgdk-pixbuf-2.0-0 >/dev/null 2>&1; then
  sudo apt-get install -y libgdk-pixbuf-2.0-0
else
  sudo apt-get install -y libgdk-pixbuf2.0-0
fi
```

</details>

<details>
<summary><b>CentOS / RHEL Installation Steps</b></summary>

```bash
sudo yum install -y pango gdk-pixbuf2 libffi-devel cairo
```

</details>

> **Tip:** When deploying with Docker (`Dockerfile`), all required Pango/Cairo system libraries are pre-installed in the image.
