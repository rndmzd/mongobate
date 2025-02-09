@echo off
REM This script runs pylint on a specific set of files and directories.
REM Modify the list below to include the desired files/directories.
set FILES=app.py app_and_db.py db.py handlers helpers chatdj chataudio utils

REM Run pylint with the selected files/directories using the specified .pylintrc file.
pylint --pylintrc .pylintrc --verbose --jobs 0 %FILES%

REM Pause at the end so you can review the output.
pause