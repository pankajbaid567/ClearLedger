# GitHub Setup Instructions

## Create GitHub Repository

1. **Go to GitHub**: https://github.com/new

2. **Repository Settings**:
   - **Name**: `ClearLedger` (or `clearledger`)
   - **Description**: `AI-powered settlement reconciliation engine for fintech. 100% precision, zero false positives. Built for Razorpay Buildathon 2026.`
   - **Visibility**: Public (for buildathon submission)
   - **Initialize**: DO NOT initialize with README, .gitignore, or license (we have these already)

3. **Add Topics** (after creation):
   ```
   fintech
   reconciliation
   payments
   settlement
   razorpay
   buildathon
   fastapi
   nextjs
   typescript
   python
   ai-powered
   ```

## Push to GitHub

After creating the repository, run these commands:

```bash
cd /Users/pankajbaid/projects/Razorpay_hackathon

# Add remote (replace YOUR_USERNAME with your GitHub username)
git remote add origin https://github.com/YOUR_USERNAME/ClearLedger.git

# Verify remote
git remote -v

# Push to GitHub
git push -u origin main
```

If you get a branch name error, your default branch might be `master` instead of `main`:

```bash
# Rename to main
git branch -M main

# Push
git push -u origin main
```

## GitHub Actions CI/CD

The repository includes `.github/workflows/ci.yml` which will automatically run:

✅ Python tests (199 tests)  
✅ TypeScript type checking  
✅ ESLint linting  
✅ Frontend build  
✅ Secret scanning  
✅ Claims verification  

The CI will run on:
- Every push to `main`
- Every pull request
- Manual workflow dispatch

## Expected CI Status

After first push, check: https://github.com/YOUR_USERNAME/ClearLedger/actions

You should see:
- ✅ Build and Test (all checks passing)
- ⏱️ Duration: ~3-5 minutes

## Secrets for CI (Optional)

If you want to test with live AI in CI:

1. Go to: Repository → Settings → Secrets and variables → Actions
2. Add secrets:
   - `AI_API_KEY` - Your AI provider API key
   - `DATABASE_URL` - Neon database URL (optional)

## Post-Push Checklist

- [ ] Repository created on GitHub
- [ ] Code pushed successfully
- [ ] GitHub Actions workflow running
- [ ] All CI checks passing
- [ ] README displaying correctly
- [ ] Topics added
- [ ] Repository is public
- [ ] Description added

## Buildathon Submission

For Razorpay Buildathon submission:

1. **Repository URL**: `https://github.com/YOUR_USERNAME/ClearLedger`
2. **Live Demo**: Deploy to Vercel/Railway/Render (optional)
3. **Demo Video**: Record walkthrough showing:
   - File upload and reconciliation
   - Exception handling
   - AI analysis (if enabled)
   - Cash position dashboard
   - Human review workflow

## Troubleshooting

### Authentication Issues

If you need to authenticate with GitHub:

**Using Personal Access Token (PAT):**
```bash
# Generate token at: https://github.com/settings/tokens
# Scopes needed: repo

# Use token as password when prompted
git push -u origin main
```

**Using SSH:**
```bash
# Add SSH key: https://github.com/settings/keys

# Change remote to SSH
git remote set-url origin git@github.com:YOUR_USERNAME/ClearLedger.git

# Push
git push -u origin main
```

### CI Failing

If GitHub Actions fail:

1. Check logs: Repository → Actions → Click on failed workflow
2. Common issues:
   - Missing dependencies (should auto-install)
   - Python version mismatch (CI uses 3.13)
   - Node version mismatch (CI uses 20.x)
3. Re-run workflow: Actions → Failed workflow → Re-run all jobs

## Verify Everything Works

After pushing:

1. **README renders**: Visit your repository homepage
2. **CI passes**: Check Actions tab
3. **Clone test**: Clone in a new location and run `make test-unit`
4. **Badge**: Add CI badge to README (optional):
   ```markdown
   ![CI](https://github.com/YOUR_USERNAME/ClearLedger/actions/workflows/ci.yml/badge.svg)
   ```

## Next Steps

After successful push:

1. ⚠️ **CRITICAL**: Rotate credentials from `.env` (they were exposed in session)
   - Generate new HuggingFace API key
   - Update Neon database password
   - Update local `.env` file

2. Create a release:
   ```bash
   git tag -a v1.0.0 -m "ClearLedger v1.0.0 - Razorpay Buildathon 2026"
   git push origin v1.0.0
   ```

3. Add README badge for version:
   ```markdown
   ![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)
   ```

4. Consider adding:
   - Contributing guidelines (CONTRIBUTING.md)
   - Code of conduct (CODE_OF_CONDUCT.md)
   - Issue templates
   - Pull request template

## Support

- **GitHub Issues**: For bugs and feature requests
- **GitHub Discussions**: For questions and community
- **Buildathon**: Submit via official Razorpay portal

Good luck with the buildathon! 🚀
