# -*- coding: utf-8 -*-
"""Pennsylvania code references and modeled geometry, not a span-table engine."""
import math

PA_CODE_URL = 'https://www.pacodeandbulletin.gov/secure/pacode/data/034/chapter403/s403.21.html'
PA_UPDATE_URL = 'https://www.pacodeandbulletin.gov/secure/pabulletin/data/vol55/55-45/1513.html'
IRC_URL = 'https://codes.iccsafe.org/content/IRC2021P2/chapter-5-floors'


def length(a,b):
    return math.hypot(b[0]-a[0],b[1]-a[1])


def crossing(a,b,c,d):
    ux,uy=b[0]-a[0],b[1]-a[1]
    vx,vy=d[0]-c[0],d[1]-c[1]
    den=ux*vy-uy*vx
    if abs(den)<1.e-8: return None
    t=((c[0]-a[0])*vy-(c[1]-a[1])*vx)/den
    q=((c[0]-a[0])*uy-(c[1]-a[1])*ux)/den
    return t if 0<=t<=1 and 0<=q<=1 else None


def review(planned):
    s=planned['settings']; joists=[]; beams=[]
    for member in planned['members']:
        if member['role'] not in ('JOIST','JOINT_SUPPORT','BORDER_SUPPORT'): continue
        actual_length=length(member['a'],member['b'])
        bearings=sorted(t for t in (crossing(member['a'],member['b'],beam['a'],beam['b'])
                                   for beam in planned.get('beams',[])) if t is not None)
        row=dict(key=member['key'],modeled_length_ft=actual_length)
        if len(bearings)==2:
            row.update(beam_center_span_ft=(bearings[1]-bearings[0])*actual_length,
                       near_center_cantilever_ft=bearings[0]*actual_length,
                       far_center_cantilever_ft=(1-bearings[1])*actual_length)
        else: row['bearing_review']='No verified pair of modeled beam crossings.'
        joists.append(row)
    for beam in planned.get('beams',[]):
        a,b=beam['a'],beam['b']; total=length(a,b)
        posts=[p for p in planned.get('posts',[]) if p.get('beam_key')==beam['key']]
        positions=sorted(((p['x']-a[0])*(b[0]-a[0])+(p['y']-a[1])*(b[1]-a[1]))/total for p in posts)
        beams.append(dict(key=beam['key'],modeled_length_ft=total,
                          post_center_spans_ft=[q-p for p,q in zip(positions,positions[1:])],
                          end_center_overhangs_ft=[positions[0],total-positions[-1]] if positions else [],
                          section_in=[s['beam_width_in'],s['beam_depth_in']]))
    return dict(reference='PA UCC / 2021 IRC, update effective 2026-01-01',verified_on='2026-10-12',
                project_jurisdiction=s.get('pa_jurisdiction','Municipality not specified'),
                status='GEOMETRY FOR REVIEW; MEMBER CAPACITY NOT CHECKED',
                sources=[PA_CODE_URL,PA_UPDATE_URL,IRC_URL],
                references=['R301.2 site criteria','R507.3 footings','R507.4 posts',
                            'R507.5 beams and effective joist span','R507.6 joist spans/cantilevers',
                            'R507.7 decking and R507.6.1 bearing','R507.6.2 lateral restraint',
                            'R311.7 stairs (PA amendments apply)','R312 guards'],
                missing_design_inputs=['Municipality and applicable permit code edition/local amendments',
                                       'Species, grade, wet service/incising, verified beam ply construction',
                                       'Site snow/wind criteria and dead/live loads',
                                       'Verified table row/footnotes or engineered/manufacturer design'],
                measurement_basis='Centerline distances only; compare code-defined clear spans, bearing and effective joist spans separately. No table interpolation or capacity pass/fail is performed.',
                joist_spacing_in=s['spacing_in'],joists=joists,beams=beams,
                post_heights_ft=[p['height_ft'] for p in planned.get('posts',[])],
                house_connections='Deferred by user; no ledger or house attachment design.')


def summary(planned):
    result=review(planned)
    spans=[j['beam_center_span_ft'] for j in result['joists'] if 'beam_center_span_ft' in j]
    beam_spans=[v for beam in result['beams'] for v in beam['post_center_spans_ft']]
    return ('PA UCC / 2021 IRC reference (effective January 1, 2026).\n'
            'Joist spacing: {0:g} in. Maximum beam-center joist span: {1}. '
            'Maximum post-center beam span: {2}.\n'
            'Centerline measurements are for review, not allowable spans. Member capacity has not been checked. '
            'Confirm species/grade, site loads, table footnotes, bearing, cantilevers, post construction and local requirements. '
            'House connections are deferred.').format(result['joist_spacing_in'],
                '{0:g} ft'.format(max(spans)) if spans else 'not available',
                '{0:g} ft'.format(max(beam_spans)) if beam_spans else 'not available')


def validate_stair_dimensions(planned):
    # PA 34 Pa. Code 403.21(a)(7)(ii); this checks only entered dimensions.
    if planned['width_ft']<3 or planned['riser_in']>8.25 or planned['tread_in']<9:
        raise ValueError('PA basic stair dimensions: at least 3 ft clear width, maximum 8.25 in riser, minimum 9 in tread. Verify handrail intrusions, headroom, nosings, landings and the selected native type separately.')
