# MIT License

# Copyright (c) 2018-2024 Nathan Letwory, Joel Putnam, Tom Svilans, Lukas Fertig

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# *** data tagging

import bpy
import json
import uuid
import rhino3dm as r3d
from mathutils import Matrix

from typing import Any, Dict, Set, Tuple


def _get_rhid(idblock):
    """Return the rhid custom property, or None if absent or invalid."""
    rhid = idblock.get("rhid", None)
    if rhid is None or rhid == "None":
        return None
    return rhid

_current_source: str = ""

def set_source(source: str) -> None:
    """Set the source identifier for the current import session."""
    global _current_source
    _current_source = source

def tag_data(
        idblock : bpy.types.ID,
        tag_dict: Dict[str, Any]
    )   -> None:
    """
    Given a Blender data idblock tag it with the id an name
    given using custom properties. These are used to track the
    relationship with original Rhino data.
    """
    guid = tag_dict.get('rhid', None)
    name = tag_dict.get('rhname', None)
    matid = tag_dict.get('rhmatid', None)
    parentid = tag_dict.get('rhparentid', None)
    is_idef = tag_dict.get('rhidef', False)
    idblock['rhid'] = str(guid)
    idblock['rhname'] = name
    idblock['rhmatid'] = str(matid)
    idblock['rhparentid'] = str(parentid)
    idblock['rhidef'] = is_idef
    idblock['rhmat_from_object'] = tag_dict.get('rhmat_from_object', True)
    idblock['rhsrc'] = _current_source

def create_tag_dict(
        guid            : uuid.UUID,
        name            : str,
        matid           : uuid.UUID = None,
        parentid        : uuid.UUID = None,
        is_idef         : bool = False,
        mat_from_object : bool = True,
) -> Dict[str, Any]:
    """
    Create a dictionary with the tag data. This can be used
    to pass to the tag_dict and get_or_create_iddata functions.

    guid and name are mandatory.
    """
    return {
        'rhid': guid,
        'rhname': name,
        'rhmatid': matid,
        'rhparentid': parentid,
        'rhidef': is_idef,
        'rhmat_from_object': mat_from_object
    }

all_dict = dict()

def clear_all_dict() -> None:
    global all_dict, _current_source
    all_dict = dict()
    _current_source = ""

def reset_all_dict(context : bpy.types.Context) -> None:
    global all_dict
    all_dict = dict()
    bases = [
        context.blend_data.objects,
        context.blend_data.cameras,
        context.blend_data.lights,
        context.blend_data.meshes,
        context.blend_data.materials,
        context.blend_data.collections,
        context.blend_data.curves
    ]
    for base in bases:
        t = repr(base).split(',')[1]
        if t in all_dict:
            dct = all_dict[t]
        else:
            dct = dict()
            all_dict[t] = dct
        for item in base:
            rhid = _get_rhid(item)
            if rhid is not None:
                dct[rhid] = item

def get_dict_for_base(base : bpy.types.bpy_prop_collection) -> Dict[str, bpy.types.ID]:
    global all_dict
    t = repr(base).split(',')[1]
    if t not in all_dict:
        pass
    return all_dict[t]

def get_or_create_iddata(
        base    : bpy.types.bpy_prop_collection,
        tag_dict: Dict[str, Any],
        obdata : bpy.types.ID,
        use_none : bool = False
    )   -> bpy.types.ID:
    """
    Get an iddata.
    The tag_dict collection should contain a guid if the goal
    is to find an existing item. If an object with given guid is found in
    this .blend use that. Otherwise new up one with base.new,
    potentially with obdata if that is set

    If obdata is given then the found object data will be set
    to that.
    """
    founditem : bpy.types.ID = None
    guid = tag_dict.get('rhid', None)
    name = tag_dict.get('rhname', None)
    matid = tag_dict.get('rhmatid', None)
    parentid = tag_dict.get('rhparentid', None)
    is_idef = tag_dict.get('rhidef', False)
    dct = get_dict_for_base(base)
    if guid is not None:
        strguid = str(guid)
        if strguid in dct:
            founditem = dct[strguid]
    if founditem:
        theitem = founditem
        theitem['rhname'] = name
        if obdata and type(theitem) != type(obdata):
            theitem.data = obdata
    else:
        if obdata or use_none:
            theitem = base.new(name=name, object_data=obdata)
        else:
            theitem = base.new(name=name)
        if guid is not None:
            strguid = str(guid)
            dct[strguid] = theitem
        tag_data(theitem, tag_dict)
    return theitem

def _collect_valid_guids(model, options=None):
    """Build a set of all valid GUIDs from the .3dm model."""
    # Imported here to avoid circular import (material.py imports utils.py)
    from .material import DEFAULT_RHINO_MATERIAL_ID, DEFAULT_RHINO_TEXT_MATERIAL_ID
    if options is None:
        options = {}
    remove_hidden_objects = options.get("remove_hidden_objects", False)
    remove_hidden_layers = options.get("remove_hidden_layers", False)
    valid = set()

    # Build set of hidden layer indices if needed
    hidden_layer_indices = set()
    for layer in model.Layers:
        if remove_hidden_layers and not layer.Visible:
            hidden_layer_indices.add(layer.Index)
        else:
            valid.add(str(layer.Id))

    for ob in model.Objects:
        if remove_hidden_objects and not ob.Attributes.Visible:
            continue
        if remove_hidden_layers and ob.Attributes.LayerIndex in hidden_layer_indices:
            continue
        valid.add(str(ob.Attributes.Id))

    for mat in model.Materials:
        valid.add(str(mat.Id))
        rc = model.RenderContent.FindId(mat.RenderMaterialInstanceId)
        if rc:
            valid.add(str(mat.RenderMaterialInstanceId))

    for idef in model.InstanceDefinitions:
        valid.add(str(idef.Id))

    valid.add(str(DEFAULT_RHINO_MATERIAL_ID))
    valid.add(str(DEFAULT_RHINO_TEXT_MATERIAL_ID))

    return valid


def _remove_stale_from(collection, valid_guids, source: str = ""):
    """Remove items from a Blender collection whose rhid is no longer valid.

    If source is given, only items tagged with that source are candidates for
    removal; items from other source files are left untouched.
    """
    to_remove = []
    for item in collection:
        rhid = _get_rhid(item)
        if rhid is None:
            continue
        if source and item.get("rhsrc", "") != source:
            continue
        if rhid not in valid_guids:
            to_remove.append(item)
    for item in to_remove:
        collection.remove(item)


def remove_stale_data(context, model, options=None):
    """Remove Blender data whose Rhino GUID is no longer in the .3dm file.

    Only objects tagged with the current source (options["rh_source"]) are
    candidates for removal; objects from other imported .3dm files are left
    untouched.
    """
    if options is None:
        options = {}
    valid_guids = _collect_valid_guids(model, options)
    source = options.get("rh_source", "")

    # Annotation text children (rhname starting with "TXT") have synthetic GUIDs
    # that don't exist in the .3dm model. We keep them as long as their parent
    # annotation object still exists, so we need the set of surviving parent rhids.
    surviving_rhids = set()
    for ob in context.blend_data.objects:
        rhid = _get_rhid(ob)
        if rhid is not None and rhid in valid_guids:
            surviving_rhids.add(rhid)

    # 1. Remove stale objects
    objects_to_remove = []
    for ob in context.blend_data.objects:
        rhid = _get_rhid(ob)
        if rhid is None:
            continue
        # Only consider objects from the current source file
        if source and ob.get("rhsrc", "") != source:
            continue
        if rhid in valid_guids:
            continue
        # Skip annotation text children whose parent annotation still exists.
        # These have rhname starting with "TXT" (set in converters/__init__.py).
        if (ob.get("rhname", "").startswith("TXT")
                and ob.parent
                and _get_rhid(ob.parent) in surviving_rhids):
            continue
        objects_to_remove.append(ob)

    for ob in objects_to_remove:
        data = ob.data
        for col in ob.users_collection:
            col.objects.unlink(ob)
        context.blend_data.objects.remove(ob)
        # Remove orphaned data blocks
        if data and data.users == 0:
            if isinstance(data, bpy.types.Mesh):
                context.blend_data.meshes.remove(data)
            elif isinstance(data, bpy.types.Curve):
                context.blend_data.curves.remove(data)
            elif isinstance(data, bpy.types.Camera):
                context.blend_data.cameras.remove(data)
            elif isinstance(data, bpy.types.Light):
                context.blend_data.lights.remove(data)

    # 2. Remove stale collections and materials (filtered by source)
    _remove_stale_from(context.blend_data.collections, valid_guids, source)
    _remove_stale_from(context.blend_data.materials, valid_guids, source)


def get_import_state(context, source: str) -> Tuple[Set[str], Set[str]]:
    """Return (imported, excluded) sets for the given source from scene state."""
    raw = context.scene.get("rh_import_state", None)
    if raw is None:
        return set(), set()
    try:
        state = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return set(), set()
    entry = state.get(source, {})
    imported = set(entry.get("imported", []))
    excluded = set(entry.get("excluded", []))
    return imported, excluded


def save_import_state(context, source: str, imported: Set[str], excluded: Set[str]) -> None:
    """Persist (imported, excluded) sets for the given source into the scene."""
    raw = context.scene.get("rh_import_state", None)
    if raw is None:
        state = {}
    else:
        try:
            state = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            state = {}
    state[source] = {
        "imported": list(imported),
        "excluded": list(excluded),
    }
    context.scene["rh_import_state"] = json.dumps(state)


def detect_new_exclusions(
        context,
        source: str,
        valid_guids: Set[str],
        previously_imported: Set[str],
        excluded: Set[str],
) -> Set[str]:
    """Detect GUIDs that were imported before but have since been manually deleted.

    A GUID counts as manually deleted when it:
    - was imported on the last run (in previously_imported)
    - is still present in the .3dm file (in valid_guids)
    - is no longer present as a Blender object tagged with this source
    - has not already been excluded

    Returns the updated excluded set.
    """
    currently_present = {
        obj["rhid"]
        for obj in context.scene.objects
        if obj.get("rhsrc", "") == source and obj.get("rhid") not in (None, "None")
    }
    newly_deleted = (previously_imported & valid_guids) - currently_present - excluded
    return excluded | newly_deleted


def matrix_from_xform(xform : r3d.Transform):
     m = Matrix(
            ((xform.M00, xform.M01, xform.M02, xform.M03),
            (xform.M10, xform.M11, xform.M12, xform.M13),
            (xform.M20, xform.M21, xform.M22, xform.M23),
            (xform.M30, xform.M31, xform.M32, xform.M33))
     )
     return m