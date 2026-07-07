# Reproducible Builds and Verification Guide

AnonyMus guarantees cryptographic auditability and transparency by enforcing **reproducible builds**. Any developer, user, or security auditor can rebuild the server package from source and verify that the resulting environment is byte-for-byte identical to the container image distributed in production.

This guide outlines the tools, configurations, and commands required to reproduce and verify the build.

---

## 1. Build Determinism Strategy

To eliminate non-determinism during the build process, AnonyMus employs three core techniques:

1. **Pinned Base Images**: The base image in `build/Dockerfile` is pinned by its unique digest (`sha256`) rather than a mutable tag. This prevents upstream OS upgrades or security patches from altering the base environment dynamically.
   - Pinned Base Image: `python:3.11-slim@sha256:d55f5f684c30c1d2e1b12b591b63d7e5d263914e667794273f7690558b3bf430`
2. **Deterministic Dependency Resolution**: All transitive Python dependencies are locked down using `pip-tools`.
   - `requirements.in` defines the top-level direct dependencies.
   - `requirements.txt` contains the fully resolved tree of direct and indirect dependency versions compiled via `pip-compile`.
3. **Reproducible Layer Layout**: Application source files are compiled without cache or variable timestamps to ensure identical layer binaries.

---

## 2. Rebuilding the Image Locally

To compile and build the container image, run the following commands from the project root:

```bash
# Clean build the Docker image
docker build --no-cache -t anonymus-local -f build/Dockerfile .
```

---

## 3. Verifying Reproducibility

To verify that two independently built images contain the exact same application file state, follow the extraction and comparison procedure:

### Step 3.1: Build and Extract Pass 1
```bash
# Build the first instance
docker build --no-cache -t anonymus-build1 -f build/Dockerfile .

# Extract the app directories
docker create --name cont1 anonymus-build1
mkdir -p /tmp/build1
docker cp cont1:/app /tmp/build1/app
docker rm cont1
```

### Step 3.2: Build and Extract Pass 2
```bash
# Build the second instance
docker build --no-cache -t anonymus-build2 -f build/Dockerfile .

# Extract the app directories
docker create --name cont2 anonymus-build2
mkdir -p /tmp/build2
docker cp cont2:/app /tmp/build2/app
docker rm cont2
```

### Step 3.3: Compare Manifest File Checksums
Run the comparison shell script (standard in Unix-like shells or WSL/git-bash):
```bash
# Clean up Python pre-compiled byte cache files (which contain dynamic run timestamps)
find /tmp/build1/app -name "__pycache__" -exec rm -rf {} +
find /tmp/build2/app -name "__pycache__" -exec rm -rf {} +

# Compute checksum lists
cd /tmp/build1/app && find . -type f -exec sha256sum {} + | sort > /tmp/manifest1.txt
cd /tmp/build2/app && find . -type f -exec sha256sum {} + | sort > /tmp/manifest2.txt

# Diff the manifests
diff -u /tmp/manifest1.txt /tmp/manifest2.txt
```

If the `diff` command produces **no output**, the builds are perfectly reproducible and verified!
This procedure is run automatically in our continuous integration pipeline (`.github/workflows/reproducible-build.yml`) on every pull request and push to the main branch.
