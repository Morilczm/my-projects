# LexiBridge AI Demo Data

This directory contains self-authored demo data for LexiBridge AI Local MVP. It is designed for reproducible course demos, smoke evaluation, and small pilot preparation.

No copyrighted textbook full text is included. The notes are short synthetic teaching examples created for this project.

## Courses

- `DS101 - Data Structures and Algorithms`
- `SP101 - Signal Processing Basics`
- `MATH101 - Engineering Mathematics`

Each course includes:

- English course notes
- Chinese reference notes
- Gold terminology items
- Negative examples for retrieval mismatch checks
- OCR/image sample placeholders
- Formula-related examples

## Demo Flow

Run from the repository root:

```bash
python scripts/migrate_db.py
python scripts/seed_demo_data.py
python scripts/run_demo_flow.py
```

For isolated test environments, set:

```bash
DATABASE_URL=sqlite:////tmp/lexibridge-demo.db
UPLOAD_FOLDER=/tmp/lexibridge-demo-uploads
```

## Generated Assets

The PNG/PDF assets are simple generated images for OCR/formula demo. They are not external learning materials.
