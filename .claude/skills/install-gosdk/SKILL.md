# Skill: install-gosdk

Install a specific GoSDK APK version on the connected tablet from Artifactory, launch the app, grant permissions, and configure developer settings.

## Trigger

User says something like:
- "install gosdk 0.9.0-rc11"
- "install 0.9.0-rc10 on tablet"
- `/install-gosdk 0.9.0-rc11`

## Required Input

| Input | Description |
|---|---|
| `version` | Full version string e.g. `0.9.0-rc11` |

If the user does not provide a version, ask for it before proceeding.

## Constants

| Value | Data |
|---|---|
| Artifactory base (release) | `https://artifactory.tomtomgroup.com/artifactory/automotive-maven-release/com/tomtom/automotive/app-gosdk` |
| Artifactory base (dev) | `https://artifactory.tomtomgroup.com/artifactory/automotive-maven-dev/com/tomtom/automotive/app-gosdk` |
| APK filename pattern | `app-gosdk-{version}.apk` |
| Package name | `com.tomtom.automotive.navigation.reference` |
| Launcher activity | `com.tomtom.automotive.navigation.reference/com.tomtom.automotive.splashactivities.SplashMainActivity` |
| Auth env var | `ARTIFACTORY_TOKEN` (set in ~/.zshrc) |

## URL selection rule

- If the version string contains `dev` (e.g. `0.10.0-dev042`), use the **dev** Artifactory base URL.
- Otherwise (e.g. `0.9.0-rc11`), use the **release** Artifactory base URL.

## Steps

Run each step sequentially. Show progress to the user after each step.

### Step 1 — Check tablet is connected

```bash
adb devices
```

If no device is listed (only the header line), stop and tell the user to connect the tablet via USB.

### Step 2 — Check if the same version is already installed

```bash
adb shell dumpsys package com.tomtom.automotive.navigation.reference | grep versionName
```

- If the package is **not found** (no output) → continue with Steps 3 and 4 to download and install.
- If the package is found, extract the version string from the output (format: `versionName=X.Y.Z-...`).
  - If the installed version **matches** the requested `{version}` exactly → skip Steps 3 and 4. Jump straight to Step 5. Tell the user the version is already installed.
  - If the installed version **differs** → continue with Steps 3 and 4 to download and install the requested version.

### Step 3 — Download APK from Artifactory

*(Skip this step if the app was already installed in Step 2)*

```bash
mkdir -p "$HOME/Downloads/APKs"

# Select base URL based on build type
if [[ "{version}" == *dev* ]]; then
  BASE_URL="https://artifactory.tomtomgroup.com/artifactory/automotive-maven-dev/com/tomtom/automotive/app-gosdk"
else
  BASE_URL="https://artifactory.tomtomgroup.com/artifactory/automotive-maven-release/com/tomtom/automotive/app-gosdk"
fi

APK_URL="$BASE_URL/{version}/app-gosdk-{version}.apk"
DEST="$HOME/Downloads/APKs/app-gosdk-{version}.apk"

curl -L -H "Authorization: Bearer $ARTIFACTORY_TOKEN" \
  "$APK_URL" \
  -o "$DEST" \
  --progress-bar
```

If curl exits non-zero or the file is smaller than 1 MB, stop and report the error.

### Step 4 — Install the downloaded APK

*(Skip this step if the app was already installed in Step 2)*

```bash
adb install -r "$HOME/Downloads/APKs/app-gosdk-{version}.apk"
```

If this returns `INSTALL_FAILED_*`, report the full error and stop.

### Step 5 — Launch the app

```bash
adb shell am start -n "com.tomtom.automotive.navigation.reference/com.tomtom.automotive.splashactivities.SplashMainActivity"
```

Wait 3 seconds for the app to start.

### Step 6 — Grant permissions

Grant all runtime permissions the app requests:

```bash
adb shell pm grant com.tomtom.automotive.navigation.reference android.permission.ACCESS_FINE_LOCATION
adb shell pm grant com.tomtom.automotive.navigation.reference android.permission.ACCESS_COARSE_LOCATION
adb shell pm grant com.tomtom.automotive.navigation.reference android.permission.READ_EXTERNAL_STORAGE
adb shell pm grant com.tomtom.automotive.navigation.reference android.permission.WRITE_EXTERNAL_STORAGE
```

Ignore "Operation not allowed" errors for permissions that are not declared in the app's manifest — those are expected.

### Step 7 — Enable developer settings via UI automation

Broadcasts do not work on any build. Use `adb shell input tap` + `uiautomator dump` to navigate the UI directly.

#### 7a — Helper: dump visible text in the right panel

Use this Python snippet after every `uiautomator dump` to extract visible text (x > 900) and toggle states:

```python
import re
content = open('/tmp/ui.xml').read()
content = content[content.find('<?xml'):]
for text, x1, y1, x2, y2 in re.findall(r'text="([^"]+)"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', content):
    if int(x1) > 900:
        print(f'({(int(x1)+int(x2))//2},{(int(y1)+int(y2))//2}) | {text}')
print('---toggles---')
for checked, x1, y1, x2, y2 in re.findall(r'checkable="true"[^>]*checked="(true|false)"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', content):
    cx, cy = (int(x1)+int(x2))//2, (int(y1)+int(y2))//2
    if cx > 900:
        print(f'({cx},{cy}) checked={checked}')
```

#### 7b — Navigate to Developer Settings

```bash
# 1. Tap the bottom-left quick-settings button
adb shell input tap 112 1243 && sleep 1

# 2. Dump UI and find the "Settings" link text position
adb shell uiautomator dump /sdcard/ui.xml && adb pull /sdcard/ui.xml /tmp/ui.xml

# 3. Tap "Settings" link (extract its center y from the dump, x is typically ~679)
#    It appears near the bottom of the quick-settings panel (text = "Settings")
adb shell input tap 679 1206 && sleep 1

# 4. Scroll the left panel down to reveal "Developer settings"
#    (it sits below "Privacy and data sharing" in the left sidebar)
adb shell input swipe 300 1200 300 500 300 && sleep 1

# 5. Tap "Developer settings" — verify position from dump first
adb shell uiautomator dump /sdcard/ui.xml && adb pull /sdcard/ui.xml /tmp/ui.xml
#    text "Developer settings" appears at approximately (383, 906) in the left panel
adb shell input tap 383 906 && sleep 1
```

After step 5, the right panel opens showing Developer Settings with a **Filter settings** search box at approximately **(1122, 346)**.

**Important keyboard note:** The filter box captures all text input, including keys during swipe gestures. Always dismiss the keyboard with `adb shell input keyevent KEYCODE_BACK` before scrolling. Use `adb shell input swipe 1600 1300 1600 700` (end point at y=700, well below filter at y=346) to scroll the right panel.

#### 7c — Enable each toggle using the filter search

For each setting below, run this pattern:

```bash
# 1. Tap filter box and clear it (30 DEL keyevents)
adb shell input tap 1122 346 && sleep 0.3
adb shell input keyevent KEYCODE_MOVE_END && sleep 0.2
for i in $(seq 1 30); do adb shell input keyevent 67; done && sleep 0.5

# 2. Type search term
adb shell input text "{search_term}" && sleep 1

# 3. Dump and find toggle
adb shell uiautomator dump /sdcard/ui.xml && adb pull /sdcard/ui.xml /tmp/ui.xml

# 4. If toggle is checked=false, tap it (toggle x is always ~2070)
adb shell input tap 2070 {toggle_y} && sleep 0.5

# 5. Dismiss keyboard before next search
adb shell input keyevent KEYCODE_BACK && sleep 0.3
```

Settings to enable and their search terms:

| Setting | Search term | Expected text in results |
|---|---|---|
| Show data source debug overlay | `data` | `Show data source debug overlay` |
| Traffic Lights Visualisation Module | `lights` | `Enable Traffic Lights Visualisation Module` |
| Traffic Signs Visualisation Module | `signs` | `Enable Traffic Signs Visualisation Module` |
| Speed limit badge | `speed limit` | `Enable speed limit badge` |

For each: after dumping, find the toggle at `x=2070` on the same row as the setting text. If `checked=false`, tap it. Verify with a second dump.

#### 7d — Enable Lane Level Navigation

First try the filter (works in newer builds like dev117+). If the filter returns no result, fall back to manual scroll.

**Try filter first:**

```bash
adb shell input tap 1122 346 && sleep 0.3
adb shell input keyevent KEYCODE_MOVE_END && sleep 0.2
for i in $(seq 1 30); do adb shell input keyevent 67; done && sleep 0.5
adb shell input text "lane level" && sleep 1
adb shell input keyevent KEYCODE_BACK && sleep 0.5
adb shell uiautomator dump /sdcard/ui.xml && adb pull /sdcard/ui.xml /tmp/ui.xml
# If "Enable Lane Level Navigation" appears with a toggle at x=2070, tap it and verify
```

**Fallback — manual scroll (if filter returns no results):**

```bash
# Clear filter
adb shell input tap 1122 346 && sleep 0.3
for i in $(seq 1 30); do adb shell input keyevent 67; done && sleep 0.3
adb shell input keyevent KEYCODE_BACK && sleep 0.5

# Scroll to top (swipe down 4 times)
for i in $(seq 1 4); do adb shell input swipe 1600 300 1600 1300 300 && sleep 0.5; done

# Scroll down until "Enable Lane Level Navigation" is visible
# (~2 scroll-downs from the top, under "Early Access Features" section)
adb shell input swipe 1600 1300 1600 700 400 && sleep 0.5
adb shell input swipe 1600 1300 1600 700 400 && sleep 0.5
adb shell uiautomator dump /sdcard/ui.xml && adb pull /sdcard/ui.xml /tmp/ui.xml
# Look for text "Enable Lane Level Navigation" and its toggle at x=2070 on the same row
# If checked=false, tap the toggle
```

#### 7e — Set Distance Units to Metric

```bash
# Search for distance
adb shell input tap 1122 346 && sleep 0.3
for i in $(seq 1 30); do adb shell input keyevent 67; done && sleep 0.3
adb shell input text "distance" && sleep 1
adb shell uiautomator dump /sdcard/ui.xml && adb pull /sdcard/ui.xml /tmp/ui.xml
# Find "Distance Unit System" — current value shows below it (e.g. "Automatic" or "Metric")
# If not already "Metric":
#   Find the clickable View next to it (x≈1588, same y as setting) and tap it
adb shell input tap 1588 {distance_setting_y} && sleep 1
#   A dialog appears with options — tap "Metric"
adb shell uiautomator dump /sdcard/ui.xml && adb pull /sdcard/ui.xml /tmp/ui.xml
# Find "Metric" text, extract its center, tap it
adb shell input tap {metric_x} {metric_y} && sleep 0.5
# Verify: dump again and confirm "Metric" now shows as the selected value
```

### Step 8 — Restart app and confirm

Some developer settings (Lane Level Navigation, Traffic Lights/Signs Visualisation Modules) require a restart to take effect. Force-stop and relaunch:

```bash
adb shell am force-stop com.tomtom.automotive.navigation.reference && sleep 1
adb shell am start -n "com.tomtom.automotive.navigation.reference/com.tomtom.automotive.splashactivities.SplashMainActivity"
```

Then tell the user:
- Whether the app was freshly installed or already present
- Version running: `{version}`
- App launched on tablet
- Permissions granted
- All 5 developer settings enabled and app restarted
