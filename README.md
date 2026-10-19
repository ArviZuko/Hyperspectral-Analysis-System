# SPECTRUM — Hyperspectral Analysis System

SPECTRUM is a PyQt6 desktop application that estimates a visible-range spectrum from an ordinary RGB image or camera feed. It uses a calibrated polynomial color transform and a compact principal-component basis to reconstruct **401 intensity values from 380 to 780 nm, at 1 nm spacing**. Users select regions of interest (ROIs), view their spectral curves, and export ROI data to Excel. The project was developed by **SpectraX (Sanket Dale)** at **Sanjivani University**, with **Arvind Mukundan** listed as mentor in the [project report](Documents/SPECTRUM_Project_Report%20%281%29.docx).

> SPECTRUM estimates spectra from RGB; it does **not** measure them with a hyperspectral camera. Different physical spectra can produce the same RGB color, so the reconstructed curve is not a substitute for a calibrated spectral measurement.

## Why the project exists

An RGB camera records three broad color channels, whereas a hyperspectral sensor samples many narrow wavelength bands. Dedicated sensors can be expensive or difficult to deploy for exploratory work. SPECTRUM explores a lower-cost software route: learn a relationship between RGB colors and reference spectra, then package that model with image capture, ROI analysis, plotting, and export tools. The research contribution described in the report is the **integration of a lightweight RGB-to-spectrum model with an interactive analysis workflow and several camera interfaces**, rather than a claim that three RGB values uniquely reveal the original spectrum.

## How it works

```text
Still image or camera frame
    → RGB conversion and 8 × 8 pixel-block averaging
    → polynomial expansion of each block's RGB values
    → regression into a six-component PCA spectral space
    → reconstruction of 401-band spectra
    → ROI masking and mean spectrum per ROI
    → live graph and Excel export
```

The supplied `weights/a.npy` through `e.npy` contain the regression matrix, six PCA basis vectors, mean spectrum, scaling values, and polynomial mode. In the current source, an image is divided into **8 × 8 pixel blocks** before reconstruction, so the resulting spectral grid is smaller than the original image. A selected ROI receives the **mean reconstructed spectrum** of the grid cells under its mask. The model produces spectral estimates for these blocks; it does not calculate an independently measured spectrum for every original pixel.

The source also defines helpers for peak wavelength, spectral energy, warm/cool labels, spectral similarity, and a rough correlated-color-temperature estimate. Some of those helpers are not connected to a visible control in the current main window. The interface does expose a multi-ROI spectral graph and an **Export Excel** action. See the [Windows application source](SRC/Window/Source%20code/app.py) for the implemented behavior and the [report](Documents/SPECTRUM_Project_Report%20%281%29.docx) for the wider research design.

## What the current interface supports

- **Inputs:** Load an image from disk or connect to a camera. The capture layer attempts standard OpenCV devices and has Raspberry Pi Picamera2 and GStreamer paths where those dependencies and devices are available.
- **ROIs:** Draw **point, rectangle, or ellipse** annotations, then zoom and compare their curves. Polygon masking exists in helper code, but the current toolbar does not offer a polygon button.
- **Visualisation:** Plot multiple ROI spectra over the 380–780 nm range in the Matplotlib panel.
- **Export:** Enter an ID, draw at least one ROI, then choose **Export Excel**. The application writes an `.xlsx` workbook to an `Exports/` directory beside the script or executable. A CSV-building helper is present in source, but the current UI exposes Excel export only.
- **Other controls:** Capture a camera frame, save the annotated image, clear annotations, or reset the session.

## Repository structure

```text
Hyperspectral-Analysis-System/
├── README.md
├── Requirement.txt
├── Documents/
│   ├── SPECTRUM_Project_Report (1).docx
│   └── SPECTRUM_Presentation.pptx
├── Screenshot/
├── SRC/
│   ├── Window/
│   │   ├── Source code/
│   │   │   ├── app.py
│   │   │   ├── logo.png, logo.ico
│   │   │   └── weights/a.npy … e.npy
│   │   ├── App/                 large executable in Release
│   │   └── installer/           Inno Setup source; large installer in Release
│   └── Raspi/
│       ├── spectrum_app.py
│       └── build_installer.bat
└── Old_Version/                earlier viewer, DLLs, and correction/light files
```

The `Old_Version/` directory is preserved as supplied. It contains an earlier Windows viewer and third-party binary libraries; it is not required by the Python source described above. The [screenshots](Screenshot/) show the supplied application views.

The project report sketches a broader layout with training data, evaluation scripts, and an output directory. **Those folders were not present in the supplied project**, so this repository does not claim to reproduce model training or quantitative validation. The application creates its own `Exports/` directory at runtime.

## Run the Windows Python source

The checked-in weights are already under the path expected by `app.py`. A typical Windows setup is:

```powershell
git clone https://github.com/ArviZuko/Hyperspectral-Analysis-System.git
cd Hyperspectral-Analysis-System
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r Requirement.txt
python "SRC\Window\Source code\app.py"
```

The five `.npy` weight files in `SRC/Window/Source code/weights/` must stay beside the application source. To analyse a still image, choose **Load Image**, draw one or more ROIs, enter an export ID, and click **Export Excel**. For live input, choose **Connect Camera**, then **Capture Image** before annotating the captured frame. Camera support depends on installed drivers and the OpenCV/Picamera2/GStreamer build available on the machine.

[`SRC/Raspi/spectrum_app.py`](SRC/Raspi/spectrum_app.py) is the Raspberry Pi variant. It uses the same broad application design, but Pi-specific camera packages and a device-specific Python environment may be needed; `Requirement.txt` alone does not install Picamera2 or a GStreamer runtime.

## Windows executable and installer

The supplied executable and installer each exceed GitHub's per-file Git limit. They are stored as independent ZIP assets in the [v1.0 Windows builds Release](https://github.com/ArviZuko/Hyperspectral-Analysis-System/releases/tag/v1.0-windows-builds):

| Original file | Download and restore instructions |
| --- | --- |
| `SRC/Window/App/HyperspectralAnalysis.exe` | [Application folder README](SRC/Window/App/README.md) |
| `SRC/Window/installer/HyperspectralAnalysis_Setup.exe` | [Installer folder README](SRC/Window/installer/README.md) |

Extract each ZIP at the **repository root** to restore its original path. The Inno Setup definitions and build script remain in Git. The binaries were uploaded as received and have not been independently tested on a clean computer.

## Evaluation and limits

The report presents example curves from multiple ROIs and describes differences between selected regions. It does **not** provide a reproducible numerical reconstruction-accuracy benchmark for the files in this repository. Because recovery from RGB is underdetermined, accuracy depends on the training spectra, camera response, exposure, white balance, and illumination. Metameric materials may remain indistinguishable. Use controlled capture conditions and validate the model against measured spectra before drawing scientific or production conclusions.

## Documentation and reuse

- [Project report](Documents/SPECTRUM_Project_Report%20%281%29.docx)
- [Presentation](Documents/SPECTRUM_Presentation.pptx)
- [Screenshots](Screenshot/)

No project-level license was supplied. Check the rights for the source, report, and older bundled binary libraries before reuse or redistribution.
