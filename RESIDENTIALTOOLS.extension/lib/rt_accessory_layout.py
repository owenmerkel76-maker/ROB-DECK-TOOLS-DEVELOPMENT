# -*- coding: utf-8 -*-
"""Pure input/quantity planning for first straight stairs and railing paths."""
import math
from rt_layout import number, EPS


def straight_stair(height_ft, width_ft, risers, tread_in):
    height=number(height_ft,'Stair rise',.1,30)
    width=number(width_ft,'Stair width',1,12)
    count=number(risers,'Riser count',2,64)
    if count!=int(count):
        raise ValueError('Riser count must be a whole number.')
    tread=number(tread_in,'Tread depth',4,24)
    return dict(height_ft=height,width_ft=width,risers=int(count),treads=int(count)-1,
                tread_in=tread,riser_in=height*12/count,run_ft=(count-1)*tread/12)


def railing_paths(poly,selected,opening_edge=-1,opening_center_ft=0,opening_width_ft=0):
    indices=set(selected)
    if not indices or any(i<0 or i>=len(poly) for i in indices):
        raise ValueError('Choose one or more valid railing edges.')
    if opening_edge>=0 and opening_edge not in indices:
        raise ValueError('Opening edge must be included in the railing selection.')
    segments=[]
    for i,a in enumerate(poly):
        if i not in indices:
            continue
        b=poly[(i+1)%len(poly)]
        length=math.hypot(b[0]-a[0],b[1]-a[1])
        if i==opening_edge:
            center=number(opening_center_ft,'Opening center',0,length)
            width=number(opening_width_ft,'Opening width',.5,length)
            lo,hi=center-width/2,center+width/2
            if lo<0 or hi>length:
                raise ValueError('Railing opening extends past its selected edge.')
            point=lambda d:(a[0]+(b[0]-a[0])*d/length,a[1]+(b[1]-a[1])*d/length)
            if lo>EPS: segments.append((a,point(lo)))
            if hi<length-EPS: segments.append((point(hi),b))
        else:
            segments.append((a,b))
    paths=[]
    for a,b in segments:
        if paths and math.hypot(a[0]-paths[-1][-1][0],a[1]-paths[-1][-1][1])<EPS:
            paths[-1].append(b)
        else:
            paths.append([a,b])
    if len(paths)>1 and math.hypot(paths[-1][-1][0]-paths[0][0][0],paths[-1][-1][1]-paths[0][0][1])<EPS:
        paths[0]=paths.pop()+paths[0][1:]
    if not paths:
        raise ValueError('The opening removes the complete railing selection.')
    return paths


def path_length(points):
    return sum(math.hypot(b[0]-a[0],b[1]-a[1]) for a,b in zip(points,points[1:]))
