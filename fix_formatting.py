import os


def fix_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Skipping file {file_path}: {e}")
        return
    fixed_lines = [line.rstrip() + "\n" for line in lines]
    # Ensure the file ends with a newline
    if fixed_lines and not fixed_lines[-1].endswith("\n"):
        fixed_lines[-1] += "\n"
    if fixed_lines != lines:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(fixed_lines)
        print(f"Fixed: {file_path}")


def main():
    targets = ["app.py", "db.py", "handlers", "helpers", "chatdj", "chataudio", "utils"]
    for target in targets:
        if os.path.isfile(target):
            fix_file(target)
        elif os.path.isdir(target):
            for root, dirs, files in os.walk(target):
                for file in files:
                    if file.endswith(".py"):
                        fix_file(os.path.join(root, file))


if __name__ == '__main__':
    main() 