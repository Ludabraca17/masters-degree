# Master's degree repository

<!-- markdownlint-disable MD033 -->
<p align="center">
  <img src="repo_image.jpg" alt="Repo logo" width="300">
</p>
<!-- markdownlint-enable MD033 -->

This repository contains files and notes taken through the duration of writing of master's degree thesis on a smart factory case study.
Important folder is named Operation_files, where all of the code files are placed. JSON_work_orders folder contains the templates of several product orders, which are expectend in the main programme. Those are primarily used by ThingsBoard devices and are here as an example  of the data this programme will process. Mixed_files folder contains severaly python files, test code and other supporting files that have been used to create this project. NodeRed folder contains the JSON of the entire NR part of the project which is in charge of local control over each of the modular production units and AMRs.

## 1. Using the repository

After cloning the repository, you will have to run the "install.ps1" in a Windows PowerShell command window. This script will create the virtual environment in the folder where the script is placed. It will also read the requirements_libraries.txt which contains the names of the important libraries used in the project, which are not already installed within the base python environment. In case the venv already exists it will simply skip the creation and finish the script.

After that you may run the "run.ps1" script which will then start the main_operation_file.py. The system is meant to be running and waiting for ThingsBoard data upon which it will start the execution of opeartions. After the completion of the tasks, you can stop the script by pressing "ctrl+c".

## 2. Notes about the operation of the system TEST

The system uses a credential.json file which is not provided for safety reasons. It contains the data for accessing ThingsBoard devices through a user which has access to them. It then reads certain attributes and extracts a production order which is then used to create a operation list, which will be sent to modular production units and AMRs. It also utilizes TB devices in order to see whether certain modular units have completed their operations and then, acording to the planned production order, sends new operations to said modular units.

Specific information about the system operation is available in the thesis on the link below:
- https://repozitorij.uni-lj.si/IzpisGradiva.php?id=176120&lang=slv