# Veilid Builds for Kunuleco

Pre-built Veilid binaries for the [Kunuleco](https://github.com/kunuleco/kunuleco) distributed communication platform.

## Why This Repo?

[Veilid](https://veilid.com/) is hosted on GitLab and doesn't provide official binary releases. This repository builds Veilid from source using GitHub Actions and publishes binaries to GitHub Releases for easy consumption by the Kunuleco installer.

## Supported Platforms

| Platform | Status | Notes |
|----------|--------|-------|
| Linux x64 | ✅ Supported | Ubuntu 22.04 build environment |
| Windows x64 | ✅ Supported | Windows Server 2022 build environment |
| macOS Intel | ⚠️ Experimental | Untested in production |
| macOS ARM64 | ⚠️ Experimental | Untested in production |

## Current Version

**Veilid 0.5.2** - See [CHANGELOG](https://gitlab.com/veilid/veilid/-/blob/main/CHANGELOG.md) for details.

Key requirements:
- Rust 1.88.0+ (MSRV)
- Cap'n Proto 1.1.0

## Usage

### For Kunuleco Users

The Kunuleco installer automatically downloads binaries from this repository. No manual action required.

### For Developers

Download binaries directly from [Releases](../../releases):

```bash
# Linux
wget https://github.com/kunuleco/veilid-builds/releases/latest/download/veilid-linux-x64.tar.gz
tar xzf veilid-linux-x64.tar.gz
./veilid-linux-x64/veilid-server --version
```

```powershell
# Windows
Invoke-WebRequest -Uri "https://github.com/kunuleco/veilid-builds/releases/latest/download/veilid-windows-x64.zip" -OutFile "veilid.zip"
Expand-Archive veilid.zip
.\veilid-windows-x64\veilid-server.exe --version
```

### Verify Checksums

Each release includes SHA256 checksums:

```bash
sha256sum -c veilid-linux-x64.tar.gz.sha256
```

## Building

See [DEPLOYMENT.md](DEPLOYMENT.md) for complete build and deployment instructions.

### Quick Start

1. Fork/clone this repository
2. Go to Actions → Build Veilid Binaries → Run workflow
3. Enter:
   - `veilid_ref`: `v0.5.2`
   - `release_tag`: `veilid-0.5.2-kunuleco.1`
4. Wait ~20 minutes for builds to complete
5. Find binaries in Releases

## License

This build system is MIT licensed. Veilid itself is [MPL-2.0](https://gitlab.com/veilid/veilid/-/blob/main/LICENSE).

## Links

- [Veilid Project](https://veilid.com/)
- [Veilid GitLab](https://gitlab.com/veilid/veilid)
- [Kunuleco](https://github.com/kunuleco/kunuleco)
