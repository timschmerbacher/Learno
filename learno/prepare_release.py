"""Build an allowlisted source-only update ZIP with SHA-256 manifest."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,zipfile
import migrate

ROOT=Path(__file__).resolve().parent
FILES=('app.py','wsgi.py','pythonanywhere_wsgi.py','v2.py','insights.py','feedback.py','migrate.py','legacy_schema.py',
       'backup.py','preflight_update.py','prepare_release.py','install_update.py','blocked_words.json','learning_sessions.csv','README.md','ONLINE_START.md',
       'test_app.py','test_v2.py','test_migration.py','test_community.py','test_activity_v4.py','test_feedback.py',
       'test_post_delete.py','test_release.py','test_account_extended.py','test_domain_extended.py','test_transport_extended.py',
       'test_browser.cjs','test_browser_extended.cjs','test_browser_v4.cjs','test_browser_feedback.cjs','test_browser_feed_stats.cjs',
       'static/index.html','static/app.js','static/v2.js','static/ui.js','static/style.css')


def build(directory=None):
    directory=Path(directory) if directory else ROOT/'releases';directory.mkdir(parents=True,exist_ok=True)
    output=directory/('learno-update-v'+str(migrate.VERSION)+'-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.zip')
    manifest={'schema_version':migrate.VERSION,'files':{}}
    with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_DEFLATED) as package:
        for filename in FILES:
            file=ROOT/filename
            if file.is_symlink() or not file.is_file():raise ValueError('Fehlende oder unsichere Quelldatei: '+filename)
            contents=file.read_bytes();manifest['files'][filename]=hashlib.sha256(contents).hexdigest()
            package.writestr('learno/'+filename,contents)
        package.writestr('learno/update-manifest.json',json.dumps(manifest,indent=2))
    with zipfile.ZipFile(output) as check:
        if check.testzip() is not None:raise ValueError('Updatepaket beschädigt.')
    return output


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir')
    print(build(parser.parse_args().output_dir))
