# TODO

- [x] ~~_Hide Reload & Test, Help & Acknolowgement_~~ [2026-09-14]
- [x] ~~_Windowed mode?_~~ not necessary [2026-09-14]
- [x] ~~_Volume rendering preset offset (https://gist.github.com/cpinter/8a1f71c7eb3ef0ebcaa6c1be6e1c9d4a#file-setpresetoffest-py)_~~ [2026-09-14]
- [ ] Implement examples, with configs + README.md
- [x] ~~_Update main README.md (examples, tree sturcure, links points to wrong location.)_~~ [2026-09-14]
- [x] ~~_Volume rendering column width adjust_~~ [2026-09-14]

"""
import vtk

def rotateSliceInPlane(sliceNode, angleDeg):
"""
A szelet nézet in-plane (a saját normálisa körüli) elforgatása.
Ez pontosan azt csinálja, amit a Reformat modul rotációs csúszkája.
"""
sliceToRAS = sliceNode.GetSliceToRAS()

    transform = vtk.vtkTransform()
    transform.SetMatrix(sliceToRAS)
    transform.RotateZ(angleDeg)   # a lokális Z (=szelet normál) tengely körül forgat

    sliceNode.GetSliceToRAS().DeepCopy(transform.GetMatrix())
    sliceNode.UpdateMatrices()

layoutManager = slicer.app.layoutManager()

redNode = layoutManager.sliceWidget("Red").mrmlSliceNode()
yellowNode = layoutManager.sliceWidget("Yellow").mrmlSliceNode()
greenNode = layoutManager.sliceWidget("Green").mrmlSliceNode()

rotateSliceInPlane(redNode, 180)
rotateSliceInPlane(yellowNode, -90)
rotateSliceInPlane(greenNode, -90)
"""
