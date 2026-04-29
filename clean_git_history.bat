@echo off
echo WARNING: This will rewrite git history and remove terraform.tfvars
echo Press Ctrl+C to cancel, or
pause

git filter-branch --force --index-filter "git rm --cached --ignore-unmatch terraform.tfvars" --prune-empty --tag-name-filter cat -- --all

echo.
echo History cleaned. Now force push with:
echo git push origin --force --all
echo git push origin --force --tags
