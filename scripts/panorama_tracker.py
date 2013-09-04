#====================== BEGIN GPL LICENSE BLOCK ======================
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
#======================= END GPL LICENSE BLOCK ========================

# <pep8 compliant>
bl_info = {
    "name": "Panorama Tracker",
    "author": "Dalai Felinto and Sebastian Koenig",
    "version": (1, 0),
    "blender": (2, 6, 8),
    "location": "Movie Clip Editor > Tools Panel",
    "description": "Help Stabilize Panorama Footage",
    "warning": "",
    "wiki_url": "",
    "tracker_url": "",
    "category": "Movie Tracking"}

import bpy
from bpy.app.handlers import persistent
from bpy.props import FloatVectorProperty, PointerProperty, BoolProperty, StringProperty

from mathutils import Euler, Vector
from math import pi

# ###############################
# Global Functions
# ###############################

def get_image(imagepath, fake_user=True):
    """get blender image for a given path, or load one"""
    image = None

    for img in bpy.data.images:
      if img.filepath == imagepath:
        image=img
        break

    if not image:
      image=bpy.data.images.load(imagepath)
      image.use_fake_user = fake_user

    return image


def context_clip(context):
    sc = context.space_data

    if sc.type != 'CLIP_EDITOR':
        return False

    if not sc.clip or not context.edit_movieclip:
        return False

    if sc.view != 'CLIP':
        return False

    return True


def marker_solo_selected(cls, context):
    movieclip = context.edit_movieclip
    tracking = movieclip.tracking.objects[movieclip.tracking.active_object_index]

    cls._selected_tracks = []
    for track in tracking.tracks:
        if track.select:
            cls._selected_tracks.append(track)

    return len(cls._selected_tracks) == 1


# ###############################
# The most important function
# ###############################
def calculate_orientation(scene):
    """return the compound orientation of the tracker + scene orientations"""

    movieclip = bpy.data.movieclips.get(scene.panorama_movieclip)
    if not movieclip: return (0,0,0)

    settings = movieclip.panorama_settings
    orientation = settings.orientation

    tracking = movieclip.tracking.objects[movieclip.tracking.active_object_index]
    focus = tracking.tracks.get(settings.focus)
    target = tracking.tracks.get(settings.target)

    if not focus or not target: return (0,0,0)

    return (-orientation[0], -orientation[1], -orientation[2])


# ###############################
# Operators
# ###############################

class CLIP_OT_panorama_camera(bpy.types.Operator):
    """"""
    bl_idname = "clip.panorama_camera"
    bl_label = "Panorama Camera"
    bl_description = "Create/adjust a panorama camera"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context_clip(context)

    def execute(self, context):
        scene = context.scene
        movieclip = context.edit_movieclip
        settings = movieclip.panorama_settings

        scene.panorama_movieclip = movieclip.name

        # 1) creates a new camera if no camera is selected
        if context.object and context.object.type == 'CAMERA' and context.object.name == 'Panorama Camera':
            camera = context.object
        else:
            camera = bpy.data.objects.new('Panorama Camera', bpy.data.cameras.new('Panorama Camera'))
            scene.objects.link(camera)

        # force render engine to be Cycles
        scene.render.engine = 'CYCLES'
        if scene.render.engine != 'CYCLES':
            self.report({'ERROR'}, "Cycles engine required.\n")
            return {'CANCELLED'}

        camera.data.type = 'PANO'
        camera.data.cycles.panorama_type = 'EQUIRECTANGULAR'

        camera.location[2] = 0.0
        camera.rotation_euler = (settings.orientation.to_matrix() * Euler((pi*0.5, 0, -pi*0.5)).to_matrix()).to_euler()
        scene.camera = camera

        imagepath = movieclip.filepath
        image = get_image(imagepath)

        if not scene.world:
            scene.world= bpy.data.worlds.new(name='Panorama')

        world = scene.world
        world.use_nodes=True
        world.cycles.sample_as_light = True
        nodetree = world.node_tree

        tex_env=nodetree.nodes.get("Panorama Environment Texture")
        if not tex_env:
            tex_env=nodetree.nodes.new('ShaderNodeTexEnvironment')
            tex_env.name = "Panorama Environment Texture"
            tex_env.location = (-200, 280)
        tex_env.image = image
        tex_env.image_user.frame_offset = 0
        tex_env.image_user.frame_start = scene.frame_start + movieclip.frame_offset
        tex_env.image_user.frame_duration = scene.frame_end
        tex_env.image_user.use_auto_refresh = True
        tex_env.image_user.use_cyclic = True

        tex_env.texture_mapping.rotation = calculate_orientation(scene)

        # Linking
        background = nodetree.nodes.get("Background")
        nodetree.links.new(tex_env.outputs[0], background.inputs[0])

        return {'FINISHED'}


class CLIP_OT_panorama_focus(bpy.types.Operator):
    """"""
    bl_idname = "clip.panorama_focus"
    bl_label = "Set Focus Marker"
    bl_description = ""
    bl_options = {'REGISTER', 'UNDO'}

    _selected_tracks = []

    @classmethod
    def poll(cls, context):
        if not context_clip(context): return False
        if not marker_solo_selected(cls, context): return False

        return True

    def execute(self, context):
        scene = context.scene
        movieclip = context.edit_movieclip
        settings = movieclip.panorama_settings

        settings.focus = self._selected_tracks[0].name
        return {'FINISHED'}


class CLIP_OT_panorama_target(bpy.types.Operator):
    """"""
    bl_idname = "clip.panorama_target"
    bl_label = "Set Target Marker"
    bl_description = ""
    bl_options = {'REGISTER', 'UNDO'}

    _selected_tracks = []

    @classmethod
    def poll(cls, context):
        if not context_clip(context): return False
        if not marker_solo_selected(cls, context): return False

        return True

    def execute(self, context):
        scene = context.scene
        movieclip = context.edit_movieclip
        settings = movieclip.panorama_settings

        settings.target = self._selected_tracks[0].name
        return {'FINISHED'}


class CLIP_PanoramaPanel(bpy.types.Panel):
    ''''''
    bl_label = "Panorama"
    bl_space_type = "CLIP_EDITOR"
    bl_region_type = "TOOLS"

    def draw(self, context):
        layout = self.layout
        movieclip = context.edit_movieclip
        settings = movieclip.panorama_settings

        col = layout.column(align=True)
        col.operator("clip.panorama_focus")
        col.operator("clip.panorama_target")

        col.separator()
        col.operator("clip.panorama_camera", icon="CAMERA_DATA")

        col.separator()
        row = col.row()
        row.prop(settings, "orientation", text="")


def update_orientation(self, context):
    """callback called every frame"""
    scene = context.scene
    world = scene.world
    if not world: return

    nodetree = world.node_tree
    tex_env=nodetree.nodes.get("Panorama Environment Texture")
    if not tex_env: return

    tex_env.texture_mapping.rotation = calculate_orientation(scene)


@persistent
def update_panorama_orientation(scene):
    world = scene.world
    if not world: return

    nodetree = world.node_tree
    tex_env=nodetree.nodes.get("Panorama Environment Texture")
    if not tex_env: return

    tex_env.texture_mapping.rotation = calculate_orientation(scene)
    debug_print(scene)


def debug_print(scene):
    """routine to print the current selected elements"""
    movieclip = bpy.data.movieclips.get(scene.panorama_movieclip)
    if not movieclip: return

    settings = movieclip.panorama_settings

    tracking = movieclip.tracking.objects[movieclip.tracking.active_object_index]
    focus = tracking.tracks.get(settings.focus)
    target = tracking.tracks.get(settings.target)

    if not focus or not target: return
    print('updating: Movieclip: {} - Focus Marker: {} - Target Marker: {}'.format(scene.panorama_movieclip, focus, target))


class TrackingPanoramaSettings(bpy.types.PropertyGroup):
    orientation= FloatVectorProperty(name="Orientation", description="Euler rotation", subtype='EULER', default=(0.0,0.0,0.0), update=update_orientation)
    focus = StringProperty()
    target = StringProperty()


# ###############################
#  Main / Register / Unregister
# ###############################
def register():
    bpy.utils.register_module(__name__)

    bpy.types.MovieClip.panorama_settings = PointerProperty(
            type=TrackingPanoramaSettings, name="Tracking Panorama Settings", description="")

    bpy.types.Scene.panorama_movieclip = StringProperty()

    bpy.app.handlers.frame_change_post.append(update_panorama_orientation)


def unregister():
    bpy.utils.unregister_module(__name__)

    del bpy.types.MovieClip.panorama_settings
    del bpy.types.Scene.panorama_movieclip

    bpy.app.handlers.frame_change_post.remove(update_panorama_orientation)


if __name__ == '__main__':
    register()
