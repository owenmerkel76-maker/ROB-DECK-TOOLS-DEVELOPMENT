# -*- coding: utf-8 -*-
"""Convex plan geometry in feet; no Revit or third-party runtime dependency."""
import math

EPS = 1.e-7


def point_inside(point,poly):
    x,y=point; inside=False
    for a,b in zip(poly,poly[1:]+poly[:1]):
        cross=(b[0]-a[0])*(y-a[1])-(b[1]-a[1])*(x-a[0])
        if abs(cross)<EPS and min(a[0],b[0])-EPS<=x<=max(a[0],b[0])+EPS and min(a[1],b[1])-EPS<=y<=max(a[1],b[1])+EPS:
            return True
        if (a[1]>y)!=(b[1]>y) and x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:
            inside=not inside
    return inside


def edge_distance(point,a,b):
    dx,dy=b[0]-a[0],b[1]-a[1]
    t=max(0,min(1,((point[0]-a[0])*dx+(point[1]-a[1])*dy)/(dx*dx+dy*dy)))
    return math.hypot(point[0]-a[0]-t*dx,point[1]-a[1]-t*dy)


def polygon(poly):
    points=[(float(p[0]),float(p[1])) for p in poly]
    if len(points)>1 and points[0]==points[-1]: points.pop()
    if len(points)<3 or len(points)>100 or any(math.isnan(v) or math.isinf(v) for p in points for v in p):
        raise ValueError('Footprint needs 3 to 100 finite vertices.')
    if any(math.hypot(b[0]-a[0],b[1]-a[1])<EPS for a,b in zip(points,points[1:]+points[:1])):
        raise ValueError('Footprint has a zero-length edge.')
    if area(points)<0: points.reverse()
    changed=True
    while changed and len(points)>3:
        changed=False
        for i,b in enumerate(points):
            a,c=points[i-1],points[(i+1)%len(points)]
            if abs((b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0]))<EPS:
                points.pop(i); changed=True; break
    def orient(a,b,c): return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    edges=list(zip(points,points[1:]+points[:1]))
    for i,(a,b) in enumerate(edges):
        for j,(c,d) in enumerate(edges):
            if j<=i or j==i+1 or (i==0 and j==len(edges)-1): continue
            ab1,ab2,cd1,cd2=orient(a,b,c),orient(a,b,d),orient(c,d,a),orient(c,d,b)
            if ab1*ab2<=EPS and cd1*cd2<=EPS and (
                    max(min(a[0],b[0]),min(c[0],d[0]))<=min(max(a[0],b[0]),max(c[0],d[0]))+EPS and
                    max(min(a[1],b[1]),min(c[1],d[1]))<=min(max(a[1],b[1]),max(c[1],d[1]))+EPS):
                raise ValueError('Footprint is self-intersecting or touches itself.')
    if area(points)<=EPS: raise ValueError('Footprint has no positive area.')
    return points


def area(poly):
    return sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(poly, poly[1:]+poly[:1]))/2.0


def convex(poly):
    points = [(float(p[0]), float(p[1])) for p in poly]
    if len(points) > 1 and points[0] == points[-1]:
        points.pop()
    if len(points) < 3 or len(points) > 100 or any(math.isnan(v) or math.isinf(v) for p in points for v in p):
        raise ValueError('Footprint needs 3 to 100 finite polygon vertices.')
    if area(points) < 0:
        points.reverse()
    for i,a in enumerate(points):
        b,c = points[(i+1)%len(points)], points[(i+2)%len(points)]
        if (b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0]) <= EPS:
            raise ValueError('Footprint must be a convex outline with straight, distinct corners; concave outlines/openings are deferred.')
    # Convexity turns alone do not reject a self-intersecting star.
    for a,b in zip(points, points[1:]+points[:1]):
        if any((b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0]) < -EPS for p in points):
            raise ValueError('Footprint is self-intersecting or non-convex.')
    return points


def clip_half(poly, normal, limit):
    result = []
    for a,b in zip(poly[-1:]+poly[:-1], poly):
        da,db = sum(a[i]*normal[i] for i in (0,1))-limit, sum(b[i]*normal[i] for i in (0,1))-limit
        if (da >= -EPS) != (db >= -EPS):
            t = da/(da-db)
            result.append((a[0]+t*(b[0]-a[0]), a[1]+t*(b[1]-a[1])))
        if db >= -EPS:
            result.append(b)
    clean = []
    for p in result:
        if not clean or math.hypot(p[0]-clean[-1][0],p[1]-clean[-1][1]) > EPS:
            clean.append(p)
    if len(clean)>1 and math.hypot(clean[0][0]-clean[-1][0],clean[0][1]-clean[-1][1]) < EPS:
        clean.pop()
    return clean


def intersect_convex(poly, boundary):
    for a,b in zip(boundary,boundary[1:]+boundary[:1]):
        n = (a[1]-b[1],b[0]-a[0])
        poly = clip_half(poly,n,a[0]*n[0]+a[1]*n[1])
        if len(poly)<3:
            return []
    return poly if abs(area(poly)) > EPS else []


def triangles(poly):
    work=list(polygon(poly)); result=[]
    while len(work)>3:
        found=False
        for i,b in enumerate(work):
            a,c=work[i-1],work[(i+1)%len(work)]
            if (b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0])<=EPS: continue
            tri=[a,b,c]
            if any(point_inside(p,tri) for p in work if p not in tri): continue
            result.append(tri); work.pop(i); found=True; break
        if not found: raise ValueError('Could not triangulate the footprint safely.')
    result.append(work); return result


def intersection_parts(subject,boundary):
    boundary=polygon(boundary)
    try:
        convex(boundary)
        result=intersect_convex(subject,boundary)
        return [result] if result else []
    except ValueError:
        pass
    fragments=[intersect_convex(subject,tri) for tri in triangles(boundary)]
    edges={}; coordinates={}
    for fragment in fragments:
        for a,b in zip(fragment,fragment[1:]+fragment[:1]):
            ka,kb=(round(a[0],8),round(a[1],8)),(round(b[0],8),round(b[1],8))
            if ka==kb: continue
            coordinates[ka]=a; coordinates[kb]=b
            if (kb,ka) in edges: del edges[(kb,ka)]
            else: edges[(ka,kb)]=True
    result=[]
    while edges:
        a,b=next(iter(edges)); del edges[(a,b)]; loop=[a,b]
        while b!=loop[0]:
            candidates=[edge for edge in edges if edge[0]==b]
            if len(candidates)!=1: raise ValueError('Clipped footprint boundary is ambiguous; no approximate rectangle will be built.')
            a,b=candidates[0]; del edges[(a,b)]; loop.append(b)
        piece=polygon([coordinates[key] for key in loop[:-1]])
        if area(piece)>EPS: result.append(piece)
    return result


def intersect(poly,boundary):
    parts=intersection_parts(poly,boundary)
    if len(parts)>1: raise ValueError('This clip creates separate board regions; use segmented planning.')
    return parts[0] if parts else []


def inset(poly, distance):
    lines = []
    for a,b in zip(poly,poly[1:]+poly[:1]):
        length = math.hypot(b[0]-a[0],b[1]-a[1])
        n = ((a[1]-b[1])/length,(b[0]-a[0])/length)
        lines.append((n,a[0]*n[0]+a[1]*n[1]+distance))
    result = []
    for (a,ka),(b,kb) in zip(lines[-1:]+lines[:-1],lines):
        det = a[0]*b[1]-a[1]*b[0]
        if abs(det)<EPS:
            raise ValueError('Parallel consecutive boundary edges cannot form a miter.')
        result.append(((ka*b[1]-a[1]*kb)/det,(a[0]*kb-ka*b[0])/det))
    result=polygon(result)
    if (area(result) <= EPS or any(not point_inside(p,poly) for p in result) or
            any(edge_distance(p,a,b)<distance-EPS for p in result for a,b in zip(poly,poly[1:]+poly[:1]))):
        raise ValueError('Border/framing inset consumes the footprint or changes its corner topology.')
    return result


def frame(settings):
    poly = settings.get('footprint_polygon') or [(0,0),(settings['run_ft'],0),
                                                (settings['run_ft'],settings['span_ft']),(0,settings['span_ft'])]
    poly = polygon(poly)
    angle = math.radians(settings.get('board_angle_deg',0)+(90 if settings['board_axis']=='B' else 0))
    c,s = math.cos(angle), math.sin(angle)
    rotated = [(c*x+s*y,-s*x+c*y) for x,y in poly]
    x0,y0 = min(p[0] for p in rotated),min(p[1] for p in rotated)
    return dict(polygon=[(x-x0,y-y0) for x,y in rotated],
                shift=(c*x0-s*y0,s*x0+c*y0), angle=angle,
                run=max(p[0] for p in rotated)-x0, span=max(p[1] for p in rotated)-y0)


def vertical_span(poly,x):
    spans=vertical_spans(poly,x)
    return spans[0] if len(spans)==1 else None


def vertical_spans(poly,x):
    hits = []
    for a,b in zip(poly,poly[1:]+poly[:1]):
        if min(a[0],b[0])-EPS <= x <= max(a[0],b[0])+EPS:
            if abs(b[0]-a[0]) < EPS:
                hits.extend([a[1],b[1]])
            else:
                t=(x-a[0])/(b[0]-a[0])
                hits.append(a[1]+t*(b[1]-a[1]))
    values=sorted(set(round(y,8) for y in hits))
    spans=[]
    for a,b in zip(values,values[1:]):
        if b-a>EPS and point_inside((x,(a+b)/2),poly):
            if spans and abs(a-spans[-1][1])<EPS: spans[-1]=(spans[-1][0],b)
            else: spans.append((a,b))
    return spans


def border_pieces(poly,width,gap,courses,stock,butt_gap,stagger=True,support_stations=None):
    """Offset miter rings; split each side into stock-limited, countable pieces."""
    pieces,seams = [],[]
    for course in range(courses):
        outer = inset(poly,course*(width+gap)) if course else poly
        inner = inset(poly,course*(width+gap)+width)
        for side,(a,b) in enumerate(zip(outer,outer[1:]+outer[:1])):
            length = math.hypot(b[0]-a[0],b[1]-a[1])
            u = ((b[0]-a[0])/length,(b[1]-a[1])/length)
            quad = [a,b,inner[(side+1)%len(poly)],inner[side]]
            # Half the miter gap on each adjoining board, normal to its cut.
            for p,q in ((a,inner[side]),(b,inner[(side+1)%len(poly)])):
                d = (q[0]-p[0],q[1]-p[1])
                n = (d[1],-d[0]); size=math.hypot(*n); n=(n[0]/size,n[1]/size)
                center = (sum(v[0] for v in quad)/len(quad),sum(v[1] for v in quad)/len(quad))
                if sum((center[i]-p[i])*n[i] for i in (0,1)) < 0:
                    n=(-n[0],-n[1])
                quad=clip_half(quad,n,p[0]*n[0]+p[1]*n[1]+butt_gap/2.0)
            projections=[p[0]*u[0]+p[1]*u[1] for p in quad]
            low,high=min(projections),max(projections)
            cuts=[low]
            first = stock/2.0 if stagger and course%2 and high-low>stock else stock
            while cuts[-1]+(first if len(cuts)==1 else stock) < high-EPS:
                target=cuts[-1]+(first if len(cuts)==1 else stock)
                if support_stations and abs(u[1])<EPS:
                    candidates=[x*u[0] for x in support_stations if cuts[-1]+.5<x*u[0]<=target+EPS]
                    if not candidates:
                        raise ValueError('No support station fits the next stock-limited border split.')
                    target=max(candidates)
                cuts.append(target)
            cuts.append(high)
            for i,(start,end) in enumerate(zip(cuts,cuts[1:])):
                lo=start+(butt_gap/2 if i else 0); hi=end-(butt_gap/2 if i<len(cuts)-2 else 0)
                piece=clip_half(clip_half(quad,u,lo),(-u[0],-u[1]),-hi)
                if len(piece)<3 or abs(area(piece))<EPS:
                    raise ValueError('Border split produced an invalid piece; revise stock/gaps.')
                pieces.append(dict(key='FRAME_C{0}_S{1}_P{2}'.format(course+1,side+1,i+1),role='BORDER',
                                   course=course+1,side=side+1,polygon=piece,axis_vector=u,
                                   edge_mode='square',width_in=width*12,length_ft=hi-lo))
                if i<len(cuts)-2:
                    # A seam support follows the width of this course, perpendicular to the side.
                    middle=(end-(a[0]*u[0]+a[1]*u[1]))
                    x,y=a[0]+u[0]*middle,a[1]+u[1]*middle
                    n=(-u[1],u[0])
                    seams.append(dict(course=course+1,side=side+1,
                                      a=(x+n[0]*gap/2,y+n[1]*gap/2),
                                      b=(x+n[0]*(width-gap/2),y+n[1]*(width-gap/2))))
    return pieces,seams
