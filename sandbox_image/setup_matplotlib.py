from pathlib import Path
import matplotlib
import shutil

# get locations
mpl_data_dir = Path(matplotlib.matplotlib_fname()).parent
mpl_font_dir = mpl_data_dir / 'fonts/ttf'
mpl_rc = mpl_data_dir / 'matplotlibrc'
# move the ttf file to taregt folder.
for font in Path('fonts').iterdir():
    shutil.move(str(font), str(mpl_font_dir))
# update config
old_rc = mpl_rc.read_text()
new_rc = old_rc.replace(
    '#font.family',
    'font.family',
).replace(  # at least support Noto Sans TC
    '#font.sans-serif     : ',
    'font.sans-serif     : Noto Sans TC, ',
).replace(
    '#axes.unicode_minus  : True',
    'axes.unicode_minus  : False',
)
with open(mpl_rc, 'w') as f:
    f.write(new_rc)
# delete the cache folder
shutil.rmtree(matplotlib.get_cachedir(), ignore_errors=True)