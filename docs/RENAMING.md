# Rename the repository and local folder to INPROFIC

The customer-facing product name is now **INPROFIC**. The internal Django
project package remains `storetrack`, so imports such as `storetrack.wsgi` keep
working and no risky package-level migration is needed.

## Rename the GitHub repository

1. Open the repository on GitHub.
2. Go to **Settings → General → Repository name**.
3. Change the name to `inprofic` and confirm the rename.
4. Update the local remote so it does not rely on GitHub's redirect:

```bash
git remote set-url origin https://github.com/<your-username>/inprofic.git
git remote -v
```

Use the SSH form instead if that is how the current remote is configured:

```bash
git remote set-url origin git@github.com:<your-username>/inprofic.git
```

Update the connected repository in Render only if Render does not follow the
GitHub rename automatically. The Blueprint service name is already `inprofic`.

## Rename the local directory

A virtual environment contains absolute paths, so move it aside before renaming
the project and create a fresh one afterwards:

```bash
deactivate 2>/dev/null || true
cd /home/wunmijordan/storetrack
mv venv ../inprofic-old-venv
cd ..
mv storetrack inprofic
cd inprofic
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python manage.py check
```

After verifying the replacement environment, the `inprofic-old-venv` folder is
only a backup and can be removed when convenient. Reopen the renamed folder in
your editor and update any absolute paths in local scripts, PythonAnywhere's
Web/WSGI configuration, and static/media mappings. Do not rename the internal
`storetrack/` Python package as part of this folder rename.
