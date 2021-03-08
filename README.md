# NotEnoughAV1Encodes-Qt
Linux GUI for AV1 Encoders - aomenc, rav1e & svt-av1

For Windows users check out the non Qt version: [NotEnoughAV1Encodes](https://github.com/Alkl58/NotEnoughAV1Encodes)

![](https://i.imgur.com/U1w21Zu.png)

### ![Linux](https://i.imgur.com/FOmiXXW.png) ![Windows](https://i.imgur.com/Ql4lP4E.png) Pre-Build

#### Stable Builds: [Releases](https://github.com/Alkl58/NotEnoughAV1Encodes-Qt/releases)

### ![Linux](https://i.imgur.com/FOmiXXW.png) Manual Installation

#### Prerequisites:
- Python >= 3.8 (recommended)
- PyQt5: `python -m pip install pyqt5`
- psutil: `python -m pip install psutil`
#### Dependencies:
- ffmpeg & ffprobe (install from your distro package manager)
- Encoders (install atleast one): [Guide](https://github.com/Alkl58/NotEnoughAV1Encodes-Qt/wiki/Encoders-Building-Guide)

*Note that the dependencies have to be in the PATH environment*
#### Finally:
- [Clone](https://github.com/Alkl58/NotEnoughAV1Encodes-Qt.git) or [Download](https://github.com/Alkl58/NotEnoughAV1Encodes-Qt/archive/main.zip) the repository 
- Run `NotEnoughAV1Encodes-Qt.py` by double click on it, or launch via the terminal: `python3 NotEnoughAV1Encodes-Qt.py`

### Development Progress:
- [X] Scene Based Splitting (FFmpeg)
- [X] Chunked Splitting
- [X] Multithreading
- [X] Multithreading with QThread
- [X] Basic aomenc encoding
- [X] Basic rav1e encoding
- [X] Basic svt-av1 encoding
- [X] Advanced aomenc settings
- [X] Advanced rav1e settings
- [X] Advanced svt-av1 settings
- [X] Custom Settings
- [X] Save & Load Custom Presets
- [X] Audio Encoding
- [ ] (Basic Subtitle Support)
- [X] Better Progress Handling
- [ ] Batch Encoding
- [X] Pause and Resume Process
- [X] Clear temp files after encode
- [X] Logging
