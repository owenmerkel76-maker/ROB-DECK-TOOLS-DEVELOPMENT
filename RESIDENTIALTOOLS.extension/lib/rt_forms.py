# -*- coding: utf-8 -*-
"""Small shared typed menu for stairs, railings and ordering options."""
import os
from pyrevit import forms
from System.Windows import Thickness,SystemParameters,TextWrapping
from System.Windows.Controls import TextBlock,TextBox,ComboBox,CheckBox,StackPanel
try: text_type=unicode
except NameError: text_type=str


class OptionsWindow(forms.WPFWindow):
    def __init__(self,title,context,fields,validator,summary,button='Continue'):
        self.result=None; self.validator=validator; self.describe=summary; self.inputs={}
        forms.WPFWindow.__init__(self,os.path.join(os.path.dirname(os.path.dirname(__file__)),'resources','ToolOptions.xaml'))
        self.Title='RESIDENTIALTOOLS | '+title; self.Heading.Text=title; self.Context.Text=context
        self.AcceptButton.Content=button
        extra_rows=sum(max(0,min(len(f.get('choices',[])),10)-1)*22 for f in fields if f.get('kind')=='checklist')
        self.Height=min(self.Height,280+48*len(fields)+extra_rows,SystemParameters.WorkArea.Height-60)
        self.MinHeight=min(self.MinHeight,self.Height)
        for field in fields:
            panel=StackPanel(); panel.Margin=Thickness(0,0,0,10)
            caption=TextBlock(); caption.Text=field['label']; caption.TextWrapping=TextWrapping.Wrap
            panel.Children.Add(caption); kind=field.get('kind','number')
            if kind=='choice':
                control=ComboBox(); choices=field['choices']; selected=0
                for i,(label,value) in enumerate(choices):
                    control.Items.Add(label)
                    if value==field.get('value'): selected=i
                control.SelectedIndex=selected if choices else -1
                self.inputs[field['key']]=(kind,control,choices)
            elif kind=='checklist':
                control=StackPanel(); choices=[]
                for label,value in field['choices']:
                    check=CheckBox(); check.Content=label; check.Margin=Thickness(0,3,0,3)
                    check.IsChecked=value in field.get('value',[]); control.Children.Add(check); choices.append((check,value))
                self.inputs[field['key']]=(kind,control,choices)
            else:
                control=TextBox(); control.Text=text_type(field.get('value',''))
                self.inputs[field['key']]=(kind,control,None)
            control.Margin=Thickness(0,4,0,0)
            if field.get('help'): control.ToolTip=field['help']
            panel.Children.Add(control); self.Fields.Children.Add(panel)

    def collect(self):
        result={}
        for key,(kind,control,choices) in self.inputs.items():
            if kind=='choice':
                if control.SelectedIndex<0: raise ValueError('Choose a value for '+key+'.')
                result[key]=choices[control.SelectedIndex][1]
            elif kind=='checklist': result[key]=[value for check,value in choices if check.IsChecked]
            else: result[key]=control.Text
        return result

    def checked(self):
        try:
            result=self.validator(self.collect()); self.Summary.Text=self.describe(result); self.Status.Text=''
            return result
        except Exception as error:
            self.Summary.Text=''; self.Status.Text=text_type(error)
            return None

    def preview(self,sender,args): self.checked()

    def accept(self,sender,args):
        result=self.checked()
        if result is not None: self.result=result; self.Close()

    def cancel(self,sender,args): self.Close()


def show(title,context,fields,validator,summary,button='Continue'):
    window=OptionsWindow(title,context,fields,validator,summary,button)
    window.ShowDialog()
    return window.result
