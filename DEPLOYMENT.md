# Veilid Build System Deployment Guide

This guide covers setting up and operating the GitHub Actions workflow for building Veilid binaries for Kunuleco.

## Overview

Since Veilid (hosted on GitLab) doesn't provide official binary releases, we build from source and publish to our own GitHub Releases. The Kunuleco installer then downloads these binaries.

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ Veilid GitLab   │────▶│ GitHub Actions   │────▶│ GitHub Releases │
│ (source)        │     │ (build)          │     │ (binaries)      │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                                         │
                                                         ▼
                                                 ┌─────────────────┐
                                                 │ Kunuleco        │
                                                 │ Installer       │
                                                 └─────────────────┘
```

## Initial Setup

### Step 1: Create the GitHub Repository

```bash
# Create a new repo on GitHub: kunuleco/veilid-builds
# Then clone it locally
git clone https://github.com/kunuleco/veilid-builds.git
cd veilid-builds
```

### Step 2: Add the Workflow File

```bash
# Create the directory structure
mkdir -p .github/workflows

# Copy the workflow file
cp build-veilid.yml .github/workflows/

# Commit and push
git add .github/workflows/build-veilid.yml
git commit -m "Add Veilid build workflow for 0.5.2"
git push origin main
```

### Step 3: Verify Repository Settings

1. Go to **Settings → Actions → General**
2. Under "Workflow permissions", select **Read and write permissions**
3. Check **Allow GitHub Actions to create and approve pull requests** (optional)

## Building Binaries

### Method A: Manual Trigger (Recommended for First Build)

1. Go to your repo on GitHub
2. Click **Actions** tab
3. Select **Build Veilid Binaries** workflow
4. Click **Run workflow**
5. Fill in the parameters:
   - `veilid_ref`: `v0.5.2` (the Veilid version to build)
   - `release_tag`: `veilid-0.5.2-kunuleco.1` (your release name)
   - `prerelease`: unchecked (unless testing)
6. Click **Run workflow**

### Method B: Tag-Based Trigger

```bash
# Create and push a tag to trigger the build
git tag veilid-v0.5.2-kunuleco.1
git push origin veilid-v0.5.2-kunuleco.1
```

### Build Duration

Expect approximately:
- Linux x64: ~10-15 minutes
- Windows x64: ~15-20 minutes
- macOS Intel: ~10-15 minutes
- macOS ARM64: ~10-15 minutes
- Total (parallel): ~20-25 minutes

## After the Build

### Step 1: Verify the Release

1. Go to **Releases** in your GitHub repo
2. Find the new release (e.g., `veilid-0.5.2-kunuleco.1`)
3. Verify all expected files are present:
   - `veilid-linux-x64.tar.gz` + `.sha256`
   - `veilid-windows-x64.zip` + `.sha256`
   - `veilid-macos-x64.tar.gz` + `.sha256`
   - `veilid-macos-arm64.tar.gz` + `.sha256`
   - `manifest-fragment.json`

### Step 2: Update Kunuleco Installer Manifest

Download `manifest-fragment.json` from the release and merge its values into your main installer manifest:

```json
{
  "binaries": {
    "veilid": {
      "0.5.2": {
        "linux-x64": {
          "url": "https://github.com/kunuleco/veilid-builds/releases/download/veilid-0.5.2-kunuleco.1/veilid-linux-x64.tar.gz",
          "sha256": "abc123...",
          "archive_type": "tar.gz",
          "executables": ["veilid-server", "veilid-cli"]
        },
        "windows-x64": {
          "url": "https://github.com/kunuleco/veilid-builds/releases/download/veilid-0.5.2-kunuleco.1/veilid-windows-x64.zip",
          "sha256": "def456...",
          "archive_type": "zip",
          "executables": ["veilid-server.exe", "veilid-cli.exe"]
        }
      }
    }
  }
}
```

### Step 3: Test the Binaries

Before updating production, test on your dev machines:

```bash
# Linux
wget https://github.com/kunuleco/veilid-builds/releases/download/veilid-0.5.2-kunuleco.1/veilid-linux-x64.tar.gz
tar xzf veilid-linux-x64.tar.gz
cd veilid-linux-x64
./veilid-server --version

# Should output: veilid-server 0.5.2
```

```powershell
# Windows (PowerShell)
Invoke-WebRequest -Uri "https://github.com/kunuleco/veilid-builds/releases/download/veilid-0.5.2-kunuleco.1/veilid-windows-x64.zip" -OutFile "veilid-windows-x64.zip"
Expand-Archive -Path "veilid-windows-x64.zip" -DestinationPath "."
cd veilid-windows-x64
.\veilid-server.exe --version
```

## Updating to a New Veilid Version

When Veilid releases a new version:

### 1. Check the Changelog

Review https://gitlab.com/veilid/veilid/-/blob/main/CHANGELOG.md for:
- Breaking API changes
- New MSRV (Minimum Supported Rust Version)
- Dependency changes

### 2. Update Workflow if Needed

If MSRV changed:
```yaml
env:
  RUST_VERSION: '1.XX.0'  # Update this
```

### 3. Run a Test Build

1. Trigger a manual build with `prerelease: true`
2. Test the binaries locally
3. Verify Kunuleco works with new version

### 4. Production Build

1. Trigger the final build with `prerelease: false`
2. Update installer manifest
3. Test installer downloads and installs correctly

## Troubleshooting

### Build Fails: Rust Version

```
error: package `veilid-core v0.5.2` cannot be built because it requires 
rustc 1.88.0 or newer
```

**Fix**: Update `RUST_VERSION` in the workflow file.

### Build Fails: Cap'n Proto

```
error: failed to run custom build command for `veilid-core`
...
capnp: command not found
```

**Fix**: The workflow installs Cap'n Proto, but verify the version matches what Veilid expects.

### Build Fails: GitLab Clone

```
fatal: unable to access 'https://gitlab.com/veilid/veilid.git/'
```

**Fix**: GitLab may be rate-limiting. Wait and retry, or check GitLab status.

### Windows Build Fails: Protobuf

```
error: could not find `protoc`
```

**Fix**: Chocolatey may have failed. Check the workflow logs for choco errors.

### macOS Builds Fail

macOS builds are marked experimental. Common issues:
- Homebrew formula changes
- Xcode version incompatibilities
- Code signing (not implemented yet)

If macOS builds fail consistently, you can disable them by removing the `build-macos-*` jobs from the workflow.

## Security Considerations

### Binary Verification

Always verify SHA256 checksums before distributing:

```bash
# Linux/macOS
sha256sum -c veilid-linux-x64.tar.gz.sha256

# Windows PowerShell
(Get-FileHash veilid-windows-x64.zip -Algorithm SHA256).Hash -eq (Get-Content veilid-windows-x64.zip.sha256).Split()[0]
```

### Future: GPG Signing

For production use, consider adding GPG signing:

1. Generate a GPG key for Kunuleco releases
2. Add the private key as a GitHub secret
3. Add a signing step to the workflow
4. Publish the public key for users to verify

## Workflow Customization

### Disable macOS Builds

Remove or comment out `build-macos-x64` and `build-macos-arm64` jobs, and remove them from the `needs` array in `create-release`.

### Add Linux ARM64 Builds

Add a new job similar to `build-linux-x64` but with:
- `runs-on: ubuntu-22.04` with QEMU, or self-hosted ARM runner
- Cross-compilation target: `aarch64-unknown-linux-gnu`

### Scheduled Builds

Add a schedule trigger to check for new Veilid releases:

```yaml
on:
  schedule:
    - cron: '0 0 * * 0'  # Weekly on Sunday
```

## Quick Reference

### Trigger a Build

```bash
# Via GitHub CLI
gh workflow run build-veilid.yml \
  -f veilid_ref=v0.5.2 \
  -f release_tag=veilid-0.5.2-kunuleco.1 \
  -f prerelease=false
```

### Check Build Status

```bash
gh run list --workflow=build-veilid.yml
```

### Download Release Artifacts

```bash
gh release download veilid-0.5.2-kunuleco.1 --pattern "*.tar.gz"
```

## Version History

| Kunuleco Release | Veilid Version | Rust | Notes |
|------------------|----------------|------|-------|
| veilid-0.5.2-kunuleco.1 | 0.5.2 | 1.88.0 | MSRV bump, logging overhaul |
| veilid-0.5.1-kunuleco.1 | 0.5.1 | 1.77.0 | Crates-only release |
| veilid-0.5.0-kunuleco.1 | 0.5.0 | 1.77.0 | Major breaking changes |
| veilid-0.4.8-kunuleco.1 | 0.4.8 | 1.77.0 | SetDHTValueOptions |
