#!/bin/bash
# This script runs pylint on a specific set of files and directories.
# Modify the list below to include the desired files/directories.
FILES=(
    "app.py"
    "app_and_db.py"
    "db.py"
    "handlers"
    "helpers"
    "chatdj"
    "chataudio"
    "utils"
)

# Run pylint using the specified .pylintrc file.
# The output (both stdout and stderr) is redirected to pylint_results.txt.
pylint --rcfile=.pylintrc "${FILES[@]}" > pylint_results.txt

echo "Pylint results have been saved to pylint_results.txt"