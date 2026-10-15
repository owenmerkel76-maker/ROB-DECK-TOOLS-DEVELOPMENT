# -*- coding: utf-8 -*-
"""Keep the original Decking-panel ribbon smoke test available."""
from Autodesk.Revit.UI import TaskDialog

TaskDialog.Show('RESIDENTIALTOOLS - Deck Design',
               'Hello World!\nThe Deck Design ribbon button is available.')
