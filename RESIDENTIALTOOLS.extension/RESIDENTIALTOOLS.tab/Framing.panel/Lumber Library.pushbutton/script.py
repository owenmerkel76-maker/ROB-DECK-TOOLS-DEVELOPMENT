# -*- coding: utf-8 -*-
"""IronPython entry point. Generate/test in temporary documents only."""
import io
import json
import os
import traceback
from datetime import datetime

from pyrevit import forms, script
from lumber_catalog import PROTOTYPES
from lumber_generator import generate_and_test


def main():
    app = __revit__.Application
    version = str(app.VersionNumber)
    if version not in ('2025', '2027'):
        forms.alert('This prototype targets Revit 2025 and 2027 only.')
        return
    template = forms.pick_file(file_ext='rft',
                               title='Select Structural Framing - Beams and Braces template')
    if not template:
        return
    destination = forms.pick_folder(title='Select output folder for prototype RFAs and logs')
    if not destination:
        return
    # A unique run directory prevents overwriting previous families/reports.
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    run_dir = os.path.join(destination, 'LumberLibrary_Revit' + version + '_' + stamp)
    os.makedirs(run_dir)
    report = dict(revit_version=version, template=template,
                  started=stamp, status='running', results=[])
    logger = script.get_logger()
    log_path = os.path.join(run_dir, 'run.log')

    def log(message):
        with io.open(log_path, 'a', encoding='utf-8') as stream:
            stream.write(u'{0} {1}\n'.format(datetime.now().isoformat(), message))

    try:
        log('Prototype adapts inspected FRAMETOOLS v0.2.2 end-plane generation; '
            'catalog and automated tests are new. Revit ' + version)
        for section in PROTOTYPES:
            result = dict(key=section['key'], section=section, status='not_tested', rfa=None)
            report['results'].append(result)
            try:
                result.update(generate_and_test(app, template, run_dir, section, log))
                result['status'] = 'passed_automated_revit_checks'
            except Exception:
                result['status'] = 'failed'
                result['error'] = traceback.format_exc()
                log(result['error'])
                logger.error('%s failed:\n%s', section['key'], result['error'])
        report['status'] = ('passed_automated_revit_checks'
                            if all(r['status'] == 'passed_automated_revit_checks'
                                   for r in report['results']) else 'failed')
    except Exception:
        report['status'] = 'failed'
        report['error'] = traceback.format_exc()
        logger.error(report['error'])
    finally:
        report_path = os.path.join(run_dir, 'report.json')
        with io.open(report_path, 'w', encoding='utf-8') as stream:
            stream.write(unicode(json.dumps(report, indent=2, ensure_ascii=False)))
    forms.alert('Lumber Library: {0}\n\nReport: {1}\nLog: {2}\n\n'
                'RFAs are version-specific. Automated checks do not certify '
                'structural capacity or manufacturer suitability.'
                .format(report['status'], report_path, log_path),
                title='Lumber Library prototype')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        script.get_logger().error(traceback.format_exc())
        forms.alert('Lumber Library could not complete. See the pyRevit output '
                    'for the full error.', title='Lumber Library error')
