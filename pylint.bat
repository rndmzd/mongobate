@echo off
REM This script runs pylint on a specific set of files and directories.
REM Modify the list below to include the desired files/directories.
set FILES=app.py app_and_db.py db.py handlers helpers chatdj chataudio utils

REM Run pylint using the specified .pylintrc file and redirect output to pylint_results.txt.
pylint --rcfile=.pylintrc %FILES% > pylint_results.txt

echo Pylint results have been saved to pylint_results.txt
pause