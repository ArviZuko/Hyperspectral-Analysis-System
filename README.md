# Hyperspectral Analysis System (SPECTRUM)

SPECTRUM is a desktop application that estimates visible-range spectra from ordinary RGB images and camera feeds. Its supplied transfer weights use polynomial color expansion and principal-component analysis to reconstruct **401 wavelength bands from 380 to 780 nm**. Users can draw regions of interest, compare spectral curves, inspect derived metrics, and export results. The [project report](Documents/SPECTRUM_Project_Report%20%281%29.docx) describes the research motivation and design; the Python sources and bundled weights in this repository show the available implementation.

The reconstructed values are **model estimates**, not direct measurements from a calibrated hyperspectral sensor. Results depend on the camera, lighting, and calibration used to create the weights.

## What is included

| Path | Contents |
| --- | --- |
| [`SRC/Window/Source code/`](SRC/Window/Source%20code/) | Windows PyQt6 source, icons, and `weights/*.npy` |
| [`SRC/Raspi/`](SRC/Raspi/) | Raspberry Pi application source and installer build script |
| [`SRC/Window/App/`](SRC/Window/App/README.md) | Windows application download guide |
| [`SRC/Window/installer/`](SRC/Window/installer/README.md) | Inno Setup scripts and installer download guide |
| [`Old_Version/`](Old_Version/) | Earlier viewer, libraries, and correction/light files supplied with the project |
| [`Documents/`](Documents/) | Project report and presentation |
| [`Screenshot/`](Screenshot/) | Application screenshots |
| [`Requirement.txt`](Requirement.txt) | Python dependencies for the supplied source |

The application source contains RGB-to-spectrum reconstruction, point/rectangle/ellipse/polygon ROI tools, spectral plots, peak wavelength and energy calculations, metameric comparison, correlated color-temperature estimation, and CSV/Excel export. Exported files are written to an `Exports` folder beside the running script or executable.

## Large Windows builds

The Windows executable and installer exceed GitHub's per-file Git limit. Download the two independent ZIP files from the [v1.0 Windows builds Release](https://github.com/ArviZuko/Hyperspectral-Analysis-System/releases/tag/v1.0-windows-builds). Each archive stores its original path and filename; extract it at the **repository root**. The [application guide](SRC/Window/App/README.md) and [installer guide](SRC/Window/installer/README.md) provide direct download links.

## Run from source

Use a Python environment compatible with the packages in `Requirement.txt`:

```powershell
git clone https://github.com/ArviZuko/Hyperspectral-Analysis-System.git
cd Hyperspectral-Analysis-System
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r Requirement.txt
python "SRC\Window\Source code\app.py"
```

The five `.npy` files in `SRC/Window/Source code/weights/` are required for reconstruction. [`SRC/Raspi/spectrum_app.py`](SRC/Raspi/spectrum_app.py) is the Raspberry Pi variant; its camera and platform dependencies may need device-specific setup. The supplied Windows binaries were uploaded as received and have not been independently tested on a clean computer.

## Documentation and scope

- [Project report](Documents/SPECTRUM_Project_Report%20%281%29.docx)
- [Presentation](Documents/SPECTRUM_Presentation.pptx)
- [Screenshots](Screenshot/)

The report discusses a broader repository layout including training and evaluation materials, but those folders were not present in the supplied project directory. This repository preserves the files that were actually provided. No project-level license was supplied; check the rights for the older bundled libraries and documents before reuse or redistribution.
