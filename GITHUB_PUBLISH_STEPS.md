# Publish this repository to GitHub

The source tree is prepared locally. It has not been pushed to a remote GitHub account, so no public repository URL is claimed here.

From this `Repository/` directory, after creating an empty GitHub repository in your account, run:

```bash
git init -b main
git add app k8s scripts results docs README.md Dockerfile .dockerignore .gitignore
git commit -m "Complete Assignment 4 milestones 1–4"
git remote add origin https://github.com/<YOUR-USERNAME>/<YOUR-REPOSITORY>.git
git push -u origin main
```

Replace the URL with the actual HTTPS URL of the empty repository you created. Then submit that real GitHub URL to the instructor.
