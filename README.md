[UofA SimRunner Getting Started.docx.md](https://github.com/user-attachments/files/31151441/UofA.SimRunner.Getting.Started.docx.md)


**Background:**

Welcome to the UofA SimRunner tutorial documentation. This guide is intended to outline the capabilities of the UofA SimRunner package and describe each feature’s functionalities. This coding package is preloaded with complementary building models and weather data from external sources, and is in no way responsible for any of these files. These are simply included as a convenience to the user. Please note that this coding package is still under development, and the latest version is available from GitHub under the following link: (https://github.com/ajordan2-sudo/UofASimRunner). If you encounter any issues using the package, please reach out directory to [ajordan2@ualberta.ca](mailto:ajordan2@ualberta.ca). 

**System Requirements:**

Before running simulations, please ensure you have the following software and python dependencies loaded onto your system:

* EnergyPlus (V25.2)  
* Python (3.12)   
* *Customtkinter* and *Pillow* (Can be installed using “pip install customtkinter Pillow”, assuming you have Python)

**Complementary Package Files:**

Included with the downloaded UofA SimRunner package are 17 IDF files representative of different building archetypes and data for 13 weather locations corresponding to different ASHRAE climate zones. 

The 17 IDF files included represent several U.S. Department of Energy reference archetypes extracted from the results of Building Technology Assessment Platform (BTAP) simulations, which is an open-source building energy simulation tool developed by Natural Resources Canada. The IDF files have been adjusted such that they work with the SimRunner package, and are no longer compatible with the original tool. For more information regarding the complementary IDF input files, please look into BTAP’s resources page.

The weather data included is taken directory from the EnergyPlus website for 13 cities of interest, each corresponding to a unique ASHRAE climate zone as depicted below in Table 1\. Please note that the current SimRunner version only works with the included complementary files. You may not add your own .IDF / .epw files for simulations. If you would like to simulation climate conditions for a different city, please consider using the corresponding city situated in the most similar ASHRAE climate zone. 

**Table 1\.** ASHRAE Climate Zones on Complementary Weather Data

| City / State | ASHRAE Climate Zone |
| ----- | :---: |
| Miami, FL | ASHRAE 1A (Very Hot / Humid) |
| Phoenix, AZ | ASHRAE 1B (Very Hot / Dry) |
| Houston, TX | ASHRAE 2A (Hot / Humid) |
| Los Angeles, CA | ASHRAE 3C (Warm / Marine) |
| Denver, CO | ASHRAE 4B (Mixed / Dry) |
| Seattle, WA | ASHRAE 4C (Mixed / Marine) |
| Chicago, IL | ASHRAE 5A (Cool / Humid) |
| Calgary, AB | ASHRAE 5B (Cool / Dry) |
| Minneapolis, MN | ASHRAE 6A (Cold / Humid) |
| Winnipeg, MB | ASHRAE 7A (Very Cold) |
| Whitehorse, YT | ASHRAE 7B (Very Cold / Dry) |
| Resolute, NU | ASHRAE 8 (Arctic) |

**Software Features:**

Upon launching UofA SimRunner.exe or running gui\_runner.py using python, you will be greeted with the window shown in Figure 1\. The GUI is split into **four** main categories (Environment Setup, Simulation Parameters, HVAC Component Generation, and Launch Controls).

Please follow the following instructions for running each simulation, which follows the order of the main four categories:

1) **Environment Setup:** To begin simulations, you must select an IDF file using the “Select IDF File” button at the top, which will bring up a list of complementary IDF files. Only 1 file may be selected per simulations. Once a file is selected, you may select which cities you wish to simulate the building in by clicking on the gray dot markers. You may hover over each marker to see the name of the city, and the marker will turn orange when selected. You may choose any number of cities per simulation, as long as one city minimum is selected. Once these options are set, click the “Verify Input File” button to verify the integrity of the complementary files before moving to the next step.  
2) **Simulation Parameters:** There are six options for simulations parameters that need to be set before each simulation. The first two options, number of iterations per hour and maximum warmup days, are values that can be adjusted to increase the speed of simulations. If you are unfamiliar with EnergyPlus, do not change these values from default. The next four values correspond to thermal transmittances of various surfaces of the building along with the average infiltration of the building. Note that thermal transmittances are in units of W/(m²⋅K), and infiltration is measured in m³/s. Multiple values for each separated by commas may be entered for each to perform parametric analysis, but at least one value must be present for each.   
3) **HVAC Component Generation:** The UofA SimRunner package has a total of 34 pre-set HVAC systems for you to select from. A brief description of each system is provided. You may pick any number of systems from the list to simulate, with all systems initially selected by default. You must always have at least 1 system selected.  
4) **Launch Controls:** With all the previous sections complete, it’s time to actually run simulations\! Based on the needs of your system, you may wish to change the run-time availability window and number of cores to increase or decrease the speed of simulations. Note that this package uses parallel processing, and automatically detects the number of cores present in your system. Once set, you may start simulations using the “Run Simulations” button, which will start the simulations run. A progress bar will appear showing the estimated time remaining and how many simulations are complete. If you need to stop simulations at any point, you may use the “Pause Run” button to stop simulations, and resume later on by using the run button again. 

**Conclusion:**

Thank you for choosing to use the UofA SimRunner coding package. 

**References:**

CanmetENERGY, Building Technology Assessment Platform (BTAP), version 2.0. \[Computer Software\]. 2026\. Available: https://github.com/canmet-energy/btap\_cli.

U.S. Department of Energy, "*EnergyPlus Weather Database*," U.S. Department of Energy. \[Online\]. Available: energyplus.net

*Disclaimer*

*The authors and University of Alberta are not liable for any issues that arise as the result of the use of this software. Use at your own risk.*
