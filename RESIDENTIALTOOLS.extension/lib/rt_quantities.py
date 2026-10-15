# -*- coding: utf-8 -*-
"""Conservative board-stock estimates; installed quantities remain separate."""
import math
from rt_layout import number, EPS


def stock_estimate(lengths,stock_ft,kerf_in=.125,end_trim_in=0):
    stock=number(stock_ft,'Stock length',1,100)
    kerf=number(kerf_in,'Saw kerf',0,1)/12
    trim=number(end_trim_in,'Total end trim per stock board (inches)',0,24)/12
    usable=stock-trim
    if usable<=0: raise ValueError('End trim consumes the entire stock board.')
    cuts=[number(v,'Piece length',.001,stock+EPS) for v in lengths]
    if any(v>usable+EPS for v in cuts): raise ValueError('A board cut exceeds usable stock after end trim.')
    remaining=[]; packed=[]
    for length in sorted(cuts,reverse=True):
        needed=length+kerf  # Kerf separates pieces sharing one stock board.
        choice=next((i for i,left in enumerate(remaining) if left+EPS>=needed),None)
        if choice is None:
            remaining.append(max(0,usable-length)); packed.append([length])
        else:
            remaining[choice]-=needed
            packed[choice].append(length)
    return dict(stock_pieces=len(remaining),installed_length_ft=sum(cuts),
                stock_length_ft=len(remaining)*stock,unallocated_length_ft=sum(remaining),
                kerf_in=kerf_in,end_trim_in=end_trim_in,cut_plan=packed,
                algorithm='First-fit decreasing by compatible stock group; kerf between pieces, entered total end trim per stock board; no ripped-width recovery or optimized nesting')


def grouped_stock(rows,stock_ft,kerf_in=.125,end_trim_in=0,extra_percent=10):
    stock=number(stock_ft,'Stock length',1,100)
    trim=number(end_trim_in,'End trim (inches)',0,24)/12
    groups={}
    for row in rows:
        if row['role'] not in ('BOARD','BORDER') or not row.get('stock_eligible',True): continue
        profile=row.get('stock_profile','Square-edge' if row['role']=='BORDER' else 'Grooved field')
        key=(profile,tuple(sorted(row.get('materials',[]))),row.get('stock_width_in',row.get('width_in','')),row.get('depth_in',''))
        groups.setdefault(key,[]).append(row['length_ft'])
    result=[]
    for key,lengths in sorted(groups.items(),key=lambda item:repr(item[0])):
        oversized=[v for v in lengths if v>stock-trim+EPS]
        if oversized:
            estimate=dict(stock_pieces=None,installed_length_ft=sum(lengths),cut_plan=[],estimate_complete=False,
                          oversized_piece_lengths_ft=oversized,order_with_allowance=None)
        else:
            estimate=stock_estimate(lengths,stock,kerf_in,end_trim_in)
            estimate.update(estimate_complete=True,order_with_allowance=allowance(estimate['stock_pieces'],extra_percent))
        estimate.update(stock_profile=key[0],materials=list(key[1]),stock_width_in=key[2],thickness_in=key[3],
                        board_stock_ft=stock,allowance_percent=extra_percent)
        result.append(estimate)
    return result


def allowance(count,percentage):
    count=number(count,'Installed/order count',0,1000000)
    pct=number(percentage,'Extra order allowance percent',0,100)
    return int(math.ceil(count*(1+pct/100.0)))


def csv_text(rows):
    try:
        text_type=unicode
    except NameError:
        text_type=str
    output=[]
    for row in rows:
        cells=[]
        for value in row:
            if isinstance(value,(str,text_type)) and value.lstrip().startswith(('=','+','-','@')):
                value=u"'"+value  # Keep external family/material names as text in spreadsheets.
            value=text_type(value)
            cells.append(u'"'+value.replace(u'"',u'""')+u'"')
        output.append(u','.join(cells))
    return u'\n'.join(output)+u'\n'
