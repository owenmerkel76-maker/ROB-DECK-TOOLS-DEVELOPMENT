# -*- coding: utf-8 -*-
"""The same settings window is shared by all three residential builders."""
import os
import math
from pyrevit import forms
from Autodesk.Revit import DB
from System.Windows import Point, Visibility, SystemParameters
from System.Windows.Media import Brushes, PointCollection
from System.Windows.Shapes import Polygon, Line, Ellipse
from System.Windows.Controls import Canvas
import rt_revit as api
import rt_simpson_catalog
import rt_geometry
import rt_code_review
import rt_presentation
from rt_layout import settings, plan


class SettingsWindow(forms.WPFWindow):
    def __init__(self, doc, anchor, values, mode):
        # Fill newly added settings from defaults when an older saved layout is opened.
        values = rt_presentation.editable_settings(values)
        self.doc, self.anchor, self.result = doc, anchor, None
        self.footprint_polygon = values.get('footprint_polygon')
        self.simpson_sources = dict(values.get('simpson_sources', {}))
        self.initializing = True
        self.syncing_block_type = False
        self.levels = sorted(DB.FilteredElementCollector(doc).OfClass(DB.Level),
                             key=lambda level: level.Elevation)
        self.joists = sorted(api.types(doc, DB.BuiltInCategory.OST_StructuralFraming),
                             key=api.symbol_name)
        self.block_types = list(self.joists)
        self.beams = list(self.joists)
        self.posts = sorted(api.types(doc, DB.BuiltInCategory.OST_StructuralColumns), key=api.symbol_name)
        self.clips = sorted(api.clip_types(doc), key=api.symbol_name)
        self.hardware = sorted(api.hardware_types(doc), key=api.symbol_name)
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            'resources', 'ResidentialSettings.xaml')
        forms.WPFWindow.__init__(self, path)
        self.Height=min(self.Height,SystemParameters.WorkArea.Height-60)
        self.MinHeight=min(self.MinHeight,self.Height)
        self.MainHeading.Text='Joist Builder' if mode=='Joist Builder' else 'Deck Designer'
        self.Title='RESIDENTIALTOOLS '+rt_presentation.release_version()+' | '+self.MainHeading.Text
        edge_note=('Edge A follows the longest straight Floor edge.' if anchor.get('source_floor_uid')
                   else 'Edge A follows the first picked edge.')
        self.FootprintSummary.Text = 'Footprint: {0}. {1} {2}'.format(
            anchor.get('source', 'three points'),
            edge_note,
            'Existing layout will be rebuilt.' if values.get('layout_id') else 'New managed layout.')
        if anchor.get('roof_projection'):
            self.FootprintSummary.Text += ' Level roof deck projected from a planar Floor; framing stays horizontal.'
        self.RoofClearance.IsEnabled = bool(anchor.get('roof_projection'))
        self.RoofClearancePanel.Visibility=Visibility.Visible if anchor.get('roof_projection') else Visibility.Collapsed
        fields = dict(LayoutName='name', RunFt='run_ft', SpanFt='span_ft',
                      HeightIn='height_in', BoardWidth='board_width_in',
                      BoardThickness='board_thickness_in', GapIn='gap_in',
                      ButtGapIn='butt_gap_in', JoistWidth='joist_width_in', JoistDepth='joist_depth_in',
                      BlockingSpacing='blocking_spacing_ft', BlockWidth='block_width_in',
                      BlockDepth='block_depth_in', HangerOffset='hanger_offset_in',
                      BeamWidth='beam_width_in', BeamDepth='beam_depth_in',
                      BeamNearSetback='beam_near_setback_ft', BeamFarSetback='beam_far_setback_ft',
                      PostWidth='post_width_in', PostDepth='post_depth_in', PostHeight='post_height_ft',
                      PostEndSetback='post_end_setback_ft', PostSpacing='post_spacing_ft', BoardAngle='board_angle_deg',
                      RoofClearance='roof_clearance_in')
        for control, key in fields.items():
            getattr(self, control).Text = api.text_type(values[key])
        self.PAJurisdiction.Text=values['pa_jurisdiction']
        self.BreakerPositions.Text=values['breaker_positions_ft']
        self.fill(self.LevelChoice, [level.Name for level in self.levels],
                  self.index_uid(self.levels, values.get('level_uid')))
        self.fill(self.BoardAxis, ['A', 'B'], ['A', 'B'].index(values['board_axis']))
        self.fill(self.BorderCourses, [1,2], [1,2].index(values['border_courses']))
        if self.footprint_polygon or anchor.get('source_floor_uid'):
            self.RunFt.IsEnabled = self.SpanFt.IsEnabled = False
            self.FootprintSummary.Text+=' Re-pick the Floor to refresh its locked extents.'
        self.fill(self.StockLength, [12, 16, 20], [12, 16, 20].index(values['stock_ft']))
        self.fill(self.Spacing, [12, 16, 24], [12, 16, 24].index(values['spacing_in']))
        categories = ['Exterior pressure-treated', 'Interior untreated', 'User-verified engineered/custom']
        self.fill(self.Exposure, categories, categories.index(values['exposure']))
        selected = self.index_uid(self.joists, values.get('joist_symbol_uid'))
        if not values.get('joist_symbol_uid'):
            desired = 'pressure_treated' if values['exposure'].startswith('Exterior') else 'untreated_dimensional'
            selected = next((i for i, symbol in enumerate(self.joists)
                             if api.type_category(symbol) == desired), selected)
        self.fill(self.JoistType, [api.symbol_name(symbol) for symbol in self.joists], selected)
        self.block_symbol_is_default = not values.get('block_symbol_uid')
        block_selected = (self.index_uid(self.block_types, values.get('block_symbol_uid'))
                          if not self.block_symbol_is_default else selected)
        self.fill(self.BlockingType, [api.symbol_name(symbol) for symbol in self.block_types], block_selected)
        self.FollowJoistType.IsChecked=self.block_symbol_is_default
        self.fill(self.BeamType, [api.symbol_name(symbol) for symbol in self.beams],
                  self.index_uid(self.beams, values.get('beam_symbol_uid')))
        self.fill(self.PostType, [api.symbol_name(symbol) for symbol in self.posts],
                  self.index_uid(self.posts, values.get('post_symbol_uid')))
        self.fill(self.ClipType, [api.symbol_name(symbol) for symbol in self.clips],
                  self.index_uid(self.clips, values['clip_symbol_uid']) if values.get('clip_symbol_uid') else -1)
        self.fill(self.ClipMode, ['Schematic solids', 'Loaded family'],
                  ['Schematic solids', 'Loaded family'].index(values['clip_mode']))
        for control, key in ((self.HangerType, 'hanger_symbol_uid'),
                             (self.DoubleHangerType, 'double_hanger_symbol_uid'),
                             (self.HurricaneType, 'hurricane_symbol_uid'),
                             (self.CornerStrapType, 'corner_strap_symbol_uid')):
            self.fill_optional(control, self.hardware, values.get(key, ''))
        for control, key in (('PictureFrame', 'picture_frame'), ('Stagger', 'stagger'),
                             ('SeamBorder', 'seam_border'),
                             ('DoubleBorderJoists', 'double_border_joists'),
                             ('BuildSupports', 'supports_enabled'),
                             ('RotateJoists','joists_follow_angle'),
                             ('Rims', 'rims'), ('Blocking', 'blocking'),
                             ('BuildBoards', 'boards_enabled'), ('BuildFraming', 'framing_enabled'),
                             ('BuildClips', 'clips_enabled')):
            getattr(self, control).IsChecked = values[key]
        self.fill(self.HangerAnchor, ['Joist bottom', 'Framing top'],
                  ['Joist bottom', 'Framing top'].index(values['hanger_anchor']))
        self.Tabs.SelectedIndex = {'Deck Builder': 0, 'Deck Designer': 0, 'Joist Builder': 1,
                                   'Deck Clip Builder': 4, 'Residential Settings': 0}[mode]
        self.initializing = False
        self.support_changed(None, None)
        self.options_changed(None,None)
        if not values.get('beam_symbol_uid'):
            self.beam_changed(None, None)
        if not values.get('post_symbol_uid'):
            self.post_changed(None, None)
        if self.block_symbol_is_default:
            self.update_block_dimensions()
        # Preserve user-provided custom dimensions when editing a stored layout.
        if not values.get('joist_symbol_uid'):
            self.joist_changed(None, None)
        else:
            self.update_joist_identity()

    @staticmethod
    def fill(control, labels, index):
        for label in labels:
            control.Items.Add(api.text_type(label))
        control.SelectedIndex = index if labels else -1

    @classmethod
    def fill_optional(cls, control, elements, uid):
        control.Items.Add('Off')
        for element in elements:
            control.Items.Add(api.text_type(api.symbol_name(element)))
        index = cls.index_uid(elements, uid) if uid else -1
        control.SelectedIndex = index + 1 if index >= 0 else 0

    @staticmethod
    def index_uid(elements, uid):
        return next((i for i, element in enumerate(elements) if element.UniqueId == uid),
                    -1 if uid else 0)

    def joist_changed(self, sender, args):
        if self.initializing or self.JoistType.SelectedIndex < 0:
            return
        dimensions = api.type_dimensions(self.joists[self.JoistType.SelectedIndex])
        if 'joist_width_in' in dimensions:
            self.JoistWidth.Text = api.text_type(dimensions['joist_width_in'])
        if 'joist_depth_in' in dimensions:
            self.JoistDepth.Text = api.text_type(dimensions['joist_depth_in'])
        self.update_joist_identity()
        if self.block_symbol_is_default and self.JoistType.SelectedIndex >= 0:
            self.syncing_block_type = True
            self.BlockingType.SelectedIndex = self.JoistType.SelectedIndex
            self.syncing_block_type = False
            self.update_block_dimensions()

    def find_joist(self,sender,args):
        names=[api.symbol_name(symbol) for symbol in self.joists]
        selected=forms.SelectFromList.show(names,title='Find loaded framing type',multiselect=False,button_name='Use joist type')
        if selected is not None: self.JoistType.SelectedIndex=names.index(selected)

    def joist_dimensions_changed(self,sender,args):
        if not self.initializing and self.block_symbol_is_default: self.update_block_dimensions()

    def follow_block_changed(self,sender,args):
        self.block_symbol_is_default=bool(self.FollowJoistType.IsChecked)
        if self.block_symbol_is_default:
            self.syncing_block_type=True
            self.BlockingType.SelectedIndex=self.JoistType.SelectedIndex
            self.syncing_block_type=False
            self.update_block_dimensions()
        self.options_changed(sender,args)

    def update_joist_identity(self):
        if self.JoistType.SelectedIndex < 0:
            self.JoistIdentity.Text = 'Load a Structural Framing family before generating joists.'
            return
        category = api.type_category(self.joists[self.JoistType.SelectedIndex])
        if category not in ('pressure_treated', 'untreated_dimensional'):
            self.Exposure.SelectedIndex = 2
            self.JoistIdentity.Text = ('Using User-verified engineered/custom for this loaded family. '
                                      'Verify section dimensions, wood/steel material and exterior treatment; '
                                      'treatment is not inferred from the family name.')
        else:
            self.JoistIdentity.Text = 'Family treatment metadata: {0}.'.format(category.replace('_', ' '))

    def blocking_changed(self, sender, args):
        if self.initializing or self.syncing_block_type or self.BlockingType.SelectedIndex < 0:
            return
        self.block_symbol_is_default = False
        self.FollowJoistType.IsChecked=False
        self.update_block_dimensions()

    def update_block_dimensions(self):
        if self.block_symbol_is_default:
            self.BlockWidth.Text=self.JoistWidth.Text; self.BlockDepth.Text=self.JoistDepth.Text
            return
        if self.BlockingType.SelectedIndex < 0:
            return
        dimensions = api.type_dimensions(self.block_types[self.BlockingType.SelectedIndex])
        if 'joist_width_in' in dimensions:
            self.BlockWidth.Text = api.text_type(dimensions['joist_width_in'])
        if 'joist_depth_in' in dimensions:
            self.BlockDepth.Text = api.text_type(dimensions['joist_depth_in'])

    def support_changed(self, sender, args):
        if not self.initializing:
            self.HurricaneType.IsEnabled = bool(self.BuildSupports.IsChecked)
            for control in ('BeamType','BeamWidth','BeamDepth','BeamNearSetback','BeamFarSetback',
                            'PostType','PostWidth','PostDepth','PostHeight','PostEndSetback','PostSpacing'):
                getattr(self,control).IsEnabled=bool(self.BuildSupports.IsChecked)

    def options_changed(self,sender,args):
        if self.initializing: return
        if not self.BuildBoards.IsChecked or not self.BuildFraming.IsChecked:
            self.BuildClips.IsChecked=False
        if not self.BuildFraming.IsChecked:
            self.BuildSupports.IsChecked=False
            for name in ('HangerType','DoubleHangerType','HurricaneType','CornerStrapType'):
                getattr(self,name).SelectedIndex=0
        self.BorderCourses.IsEnabled=bool(self.PictureFrame.IsChecked and self.BuildBoards.IsChecked)
        self.BreakerPositions.IsEnabled=bool(self.SeamBorder.IsChecked and self.BuildBoards.IsChecked)
        self.DoubleBorderJoists.IsEnabled=bool(self.PictureFrame.IsChecked and self.BuildFraming.IsChecked)
        self.BlockingSpacing.IsEnabled=bool(self.Blocking.IsChecked and self.BuildFraming.IsChecked)
        self.BlockingType.IsEnabled=bool(self.BuildFraming.IsChecked and not self.block_symbol_is_default)
        self.BlockWidth.IsReadOnly=self.BlockDepth.IsReadOnly=self.block_symbol_is_default
        self.ClipType.IsEnabled=bool(self.BuildClips.IsChecked and str(self.ClipMode.SelectedItem)=='Loaded family')
        for name in ('HangerType','DoubleHangerType','CornerStrapType'):
            getattr(self,name).IsEnabled=bool(self.BuildFraming.IsChecked)
        self.BuildSupports.IsEnabled=bool(self.BuildFraming.IsChecked)
        self.support_changed(sender,args)

    def beam_changed(self, sender, args):
        if not self.initializing and self.BeamType.SelectedIndex >= 0:
            dimensions = api.type_dimensions(self.beams[self.BeamType.SelectedIndex])
            if 'joist_width_in' in dimensions:
                self.BeamWidth.Text = api.text_type(dimensions['joist_width_in'])
            if 'joist_depth_in' in dimensions:
                self.BeamDepth.Text = api.text_type(dimensions['joist_depth_in'])

    def post_changed(self, sender, args):
        if not self.initializing and self.PostType.SelectedIndex >= 0:
            dimensions = api.post_dimensions(self.posts[self.PostType.SelectedIndex])
            if 'joist_width_in' in dimensions:
                self.PostWidth.Text = api.text_type(dimensions['joist_width_in'])
            if 'joist_depth_in' in dimensions:
                self.PostDepth.Text = api.text_type(dimensions['joist_depth_in'])

    def collect(self, validate_layout=True):
        result = dict(name=self.LayoutName.Text, run_ft=self.RunFt.Text, span_ft=self.SpanFt.Text,
                      pa_jurisdiction=self.PAJurisdiction.Text,
                      breaker_positions_ft=self.BreakerPositions.Text,
                      height_in=self.HeightIn.Text, board_axis=api.text_type(self.BoardAxis.SelectedItem),
                      board_width_in=self.BoardWidth.Text, board_thickness_in=self.BoardThickness.Text,
                      gap_in=self.GapIn.Text, butt_gap_in=self.ButtGapIn.Text,
                      stock_ft=self.StockLength.SelectedItem, spacing_in=self.Spacing.SelectedItem,
                      exposure=api.text_type(self.Exposure.SelectedItem),
                      joist_width_in=self.JoistWidth.Text, joist_depth_in=self.JoistDepth.Text,
                      blocking_spacing_ft=self.BlockingSpacing.Text,
                      block_width_in=self.BlockWidth.Text, block_depth_in=self.BlockDepth.Text,
                      clip_mode=api.text_type(self.ClipMode.SelectedItem),
                      hanger_anchor=api.text_type(self.HangerAnchor.SelectedItem),
                      hanger_offset_in=self.HangerOffset.Text,
                      board_angle_deg=self.BoardAngle.Text, border_courses=self.BorderCourses.SelectedItem,
                      footprint_polygon=self.footprint_polygon,
                      roof_clearance_in=self.RoofClearance.Text,
                      beam_width_in=self.BeamWidth.Text, beam_depth_in=self.BeamDepth.Text,
                      beam_near_setback_ft=self.BeamNearSetback.Text, beam_far_setback_ft=self.BeamFarSetback.Text,
                      post_width_in=self.PostWidth.Text, post_depth_in=self.PostDepth.Text,
                      post_height_ft=self.PostHeight.Text, post_end_setback_ft=self.PostEndSetback.Text,
                      post_spacing_ft=self.PostSpacing.Text)
        for control, key in ((self.HangerType, 'hanger_symbol_uid'),
                             (self.DoubleHangerType, 'double_hanger_symbol_uid'),
                             (self.HurricaneType, 'hurricane_symbol_uid'),
                             (self.CornerStrapType, 'corner_strap_symbol_uid')):
            result[key] = (self.hardware[control.SelectedIndex - 1].UniqueId
                           if control.SelectedIndex > 0 else '')
        for control, key in (('PictureFrame', 'picture_frame'), ('Stagger', 'stagger'),
                             ('SeamBorder', 'seam_border'),
                             ('DoubleBorderJoists', 'double_border_joists'),
                             ('BuildSupports', 'supports_enabled'),
                             ('RotateJoists','joists_follow_angle'),
                             ('Rims', 'rims'), ('Blocking', 'blocking'),
                             ('BuildBoards', 'boards_enabled'), ('BuildFraming', 'framing_enabled'),
                             ('BuildClips', 'clips_enabled')):
            result[key] = bool(getattr(self, control).IsChecked)
        for control, elements, key in ((self.LevelChoice, self.levels, 'level_uid'),
                                        (self.JoistType, self.joists, 'joist_symbol_uid'),
                                        (self.BlockingType, self.block_types, 'block_symbol_uid'),
                                        (self.BeamType, self.beams, 'beam_symbol_uid'),
                                        (self.PostType, self.posts, 'post_symbol_uid'),
                                        (self.ClipType, self.clips, 'clip_symbol_uid')):
            result[key] = elements[control.SelectedIndex].UniqueId if control.SelectedIndex >= 0 else ''
        result['simpson_sources'] = dict((role, source) for role, source in self.simpson_sources.items()
                                        if result.get(rt_simpson_catalog.ROLE_KEYS.get(role)) ==
                                        source.get('unique_id'))
        if self.block_symbol_is_default:
            result['block_symbol_uid']=''
            result['block_width_in']=result['joist_width_in']; result['block_depth_in']=result['joist_depth_in']
        return settings(result) if validate_layout else result

    def validate_simpson(self, values):
        uid = values.get('joist_symbol_uid')
        symbol = self.doc.GetElement(uid) if uid else None
        category = api.type_category(symbol) if symbol is not None else None
        rt_simpson_catalog.validate_selections(values, category)

    def preview(self, sender, args):
        try:
            self.CountSummary.Text=''
            self.LayoutCanvas.Children.Clear()
            result = plan(self.collect())
            s = result['settings']
            self.draw_preview(result)
            issues=[]
            for check in (lambda:self.validate_simpson(s),lambda:api.validate_type(self.doc,s),
                          lambda:api.validate_support_types(self.doc,s),lambda:api.validate_clip_type(self.doc,s)):
                try: check()
                except Exception as error: issues.append(api.text_type(error))
            for uid, label in ((s['hanger_symbol_uid'], 'joist hangers'),
                               (s['double_hanger_symbol_uid'], 'double joist hangers'),
                               (s['hurricane_symbol_uid'], 'hurricane straps'),
                               (s['corner_strap_symbol_uid'], 'corner straps')):
                try: api.validate_hardware_type(self.doc, uid, label)
                except Exception as error: issues.append(api.text_type(error))
            self.CountSummary.Text=rt_presentation.count_text(result['counts'],sum(b.get('border_kind')=='breaker' for b in result['boards']))
            self.Status.Text=('Before building: '+' '.join(issues)+'\n' if issues else '')+' '.join(result['warnings'])
            self.Status.Foreground=Brushes.Firebrick if issues else Brushes.DarkSlateGray
            self.Tabs.SelectedIndex=4
        except Exception as error:
            self.Status.Text = api.text_type(error)
            self.Status.Foreground=Brushes.Firebrick

    def draw_preview(self,planned):
        self.LayoutCanvas.Children.Clear()
        width=self.LayoutCanvas.ActualWidth or 600
        height=self.LayoutCanvas.Height
        scale=min((width-20)/planned['run'],(height-20)/planned['span'])
        def point(x,y): return Point(10+x*scale,height-10-y*scale)
        def polygon(points,brush,fill=None):
            shape=Polygon(); shape.Points=PointCollection()
            for x,y in points: shape.Points.Add(point(x,y))
            shape.Stroke=brush; shape.StrokeThickness=1
            if fill is not None: shape.Fill=fill; shape.Opacity=.4
            self.LayoutCanvas.Children.Add(shape)
        def line(a,b,brush,thickness=1):
            start,end=point(*a),point(*b); shape=Line()
            shape.X1,shape.Y1,shape.X2,shape.Y2=start.X,start.Y,end.X,end.Y
            shape.Stroke=brush; shape.StrokeThickness=thickness; self.LayoutCanvas.Children.Add(shape)
        polygon(rt_geometry.frame(planned['settings'])['polygon'],Brushes.Black)
        # Large previews sample board/clip graphics while retaining full counts.
        board_step=max(1,int(math.ceil(len(planned['boards'])/600.0)))
        for board in planned['boards'][::board_step]:
            outline=board.get('polygon') or [(board['start'],board['low']),(board['end'],board['low']),
                                            (board['end'],board['high']),(board['start'],board['high'])]
            brush=Brushes.DarkOrange if board['role']=='BORDER' else Brushes.SaddleBrown
            polygon(outline,brush,brush)
        for member in planned['members']+planned.get('beams',[]):
            line(member['a'],member['b'],Brushes.DarkBlue,3 if member['role']=='BEAM' else 1)
        for post in planned.get('posts',[]):
            angle=math.radians(post.get('rotation_deg',0)); c,s=math.cos(angle),math.sin(angle)
            polygon([(post['x']+c*x-s*y,post['y']+s*x+c*y) for x,y in
                     [(-post['width_in']/24,-post['depth_in']/24),(post['width_in']/24,-post['depth_in']/24),
                      (post['width_in']/24,post['depth_in']/24),(-post['width_in']/24,post['depth_in']/24)]],Brushes.ForestGreen,Brushes.ForestGreen)
        for item in planned['hardware']:
            pt=point(item['x'],item['y']); dot=Ellipse(); dot.Width=dot.Height=4; dot.Fill=Brushes.Crimson
            Canvas.SetLeft(dot,pt.X-2); Canvas.SetTop(dot,pt.Y-2)
            self.LayoutCanvas.Children.Add(dot)
        self.PreviewLegend.Text='Plan aligned to decking: brown boards, orange borders, blue framing/beams, green posts, red hardware insertion points. Board sample step: {0}.'.format(board_step)

    def code_reference(self,sender,args):
        try:
            self.Status.Text=rt_code_review.summary(plan(self.collect()))
            choice=forms.CommandSwitchWindow.show(['PA adopted code and amendments','2021 IRC deck provisions'],
                                                   message='Pennsylvania deck reference | open official source')
            if choice:
                os.startfile(rt_code_review.PA_CODE_URL if choice.startswith('PA') else rt_code_review.IRC_URL)
        except Exception as error:
            self.Status.Text=api.text_type(error)

    def finish(self, action):
        try:
            values = self.collect(validate_layout=(action == 'build'))
            if action == 'build':
                self.validate_simpson(values)
                planned = plan(values)
                api.validate_type(self.doc, values)
                api.validate_support_types(self.doc, values)
                api.validate_clip_type(self.doc, values)
                for uid, label in ((values['hanger_symbol_uid'], 'joist hangers'),
                                   (values['double_hanger_symbol_uid'], 'double joist hangers'),
                                   (values['hurricane_symbol_uid'], 'hurricane straps'),
                                   (values['corner_strap_symbol_uid'], 'corner straps')):
                    api.validate_hardware_type(self.doc, uid, label)
            else:
                planned = None
            self.result = dict(action=action, settings=values, planned=planned,tab_index=self.Tabs.SelectedIndex)
            self.Close()
        except Exception as error:
            self.Status.Text = api.text_type(error)
            self.Status.Foreground=Brushes.Firebrick

    def help(self,sender,args):
        forms.alert('1. Choose the Floor outline or rectangle and board direction.\n'
                    '2. Select loaded framing types and verify their actual dimensions.\n'
                    '3. Add borders, breaker positions, blocking, supports and optional hardware.\n'
                    '4. Preview the plan and counts, then build or rebuild.\n\n'
                    'Breaker positions are feet along the framing layout axis. Blank uses stock splits.\n'
                    'Double hangers serve touching pairs; beam ties require modeled beams.\n'
                    'Rebuild replaces owned pieces. Rerun stairs/railings after deck changes.\n'
                    'Material List reports installed quantities and a separate ordering estimate.',
                    title='RESIDENTIALTOOLS | Workflow guide')

    def build(self, sender, args):
        self.finish('build')

    def repick(self, sender, args):
        self.finish('repick')

    def create_clip(self, sender, args):
        # Family generation is independent of enabled model components/settings.
        self.finish('clip_family')

    def simpson_library(self, sender, args):
        self.finish('simpson_library')

    def cancel(self, sender, args):
        self.Close()


def show(doc, anchor, values, mode,initial_tab=None):
    window = SettingsWindow(doc, anchor, values, mode)
    if initial_tab is not None: window.Tabs.SelectedIndex=initial_tab
    window.ShowDialog()
    return window.result
