# Q1 delivery plotting dependencies

`figure_skill/` contains byte-for-byte copies of the scripts actually used from the user-requested math-modeling skill, upstream repository https://github.com/XiaoMaColtAI/math-modeling-skill . The installed skill was frozen at upstream commit `e0f3e83dc241fe4d7d43be32d800a61db13b1439` according to the project setup record. No source changes were made to these helpers.

| Local file | Source path relative to the installed skill |
|---|---|
| setup_style.py | tools/figure/scripts/setup_style.py |
| export_figure.py | tools/figure/scripts/export_figure.py |
| visual_qa.py | tools/figure/scripts/visual_qa.py |
| profile_data.py | tools/figure/scripts/profile_data.py |
| check_figure.py | tools/figure/scripts/check_figure.py |
| figure_audit.py | references/roles/编程手/scripts/figure_audit.py |

The upstream script docstrings, comments and attribution are preserved. No root or figure-specific license file was present in the installed skill copy; this directory does not add or claim a new license for those scripts. The delivery manifest records the actual copied file hashes.

`fonts/NotoSansSC.ttf` was downloaded from https://raw.githubusercontent.com/google/fonts/main/ofl/notosanssc/NotoSansSC%5Bwght%5D.ttf . Its original SIL Open Font License is included as `fonts/OFL.txt`. A static weight-400 instance, `fonts/NotoSansSC-Regular.ttf`, was generated with `fonttools varLib.instancer NotoSansSC.ttf wght=400 --output NotoSansSC-Regular.ttf` for Matplotlib compatibility. The plotting script registers the static local font at runtime without modifying system fonts. Its content hash is recorded in `others/figure_contracts.json` and the delivery manifest. FontTools is needed only to regenerate the font instance, not to run the delivery script.

The plotting script uses the helper's exact-size export with `tight=False`. Grayscale QA images are derived separately with Pillow because the helper's built-in grayscale path rewrites the main PNG using tight cropping. This preserves the intended 7.2-inch publication width. QA grayscale images live in `others/visual_qa/`, not in the nine-figure candidate count.
