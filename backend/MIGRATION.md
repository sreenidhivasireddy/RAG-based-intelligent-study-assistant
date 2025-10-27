# Migration Guide: Switch to Project-local Virtual Environment

If you were using a virtual environment in a different location (e.g., `~/.venvs/myenv`), follow these steps to migrate to the project-local `venv`.

## Quick Migration Steps

### 1. Create New Virtual Environment in Project Root

```bash
# Navigate to project root
cd /path/to/RAG-based-intelligent-study-assistant

# Create venv in project root
python3 -m venv venv

# Activate it
source venv/bin/activate
```

### 2. Install Dependencies

```bash
# Install all dependencies
pip install -r requirements.txt
```

### 3. Verify Installation

```bash
# Check that packages are installed
pip list | grep -E "redis|fastapi|minio"

# Should see:
# fastapi    0.120.0
# minio      7.2.18
# redis      7.0.0
```

### 4. Update Your Workflow

From now on, always activate from project root:

```bash
# Before starting server or running tests:
source venv/bin/activate
```

### 5. (Optional) Remove Old Virtual Environment

If you no longer need the old virtual environment:

```bash
# Only if you're sure you don't need it
rm -rf ~/.venvs/myenv
```

## New Standard Workflow

### Start Server
```bash
cd /path/to/RAG-based-intelligent-study-assistant
source venv/bin/activate
cd backend
./start_server.sh
```

### Run Tests
```bash
cd /path/to/RAG-based-intelligent-study-assistant
source venv/bin/activate
cd backend
./run_tests.sh
```

## Benefits of Project-local venv

✅ **Portable**: Works on any machine, just clone and create venv  
✅ **Isolated**: Each project has its own dependencies  
✅ **Simple**: No need to remember custom paths  
✅ **Standard**: Follows Python community best practices  
✅ **Git-ignored**: Already configured in `.gitignore`

## Troubleshooting

**Q: I'm in the wrong virtual environment**
```bash
# Deactivate current environment
deactivate

# Activate project venv
source venv/bin/activate
```

**Q: Scripts say virtual environment not activated**
```bash
# Check current environment
echo $VIRTUAL_ENV

# Should show: /path/to/RAG-based-intelligent-study-assistant/venv
```

**Q: Want to use a different location?**

You can create venv anywhere and modify the scripts/README accordingly. But we recommend keeping it in project root for simplicity.

