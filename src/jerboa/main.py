import imgui
import pyglet
from imgui.integrations.pyglet import create_renderer

# from testwindow import show_test_window
from jerboa.avsource import SLSource
# from player import SLPlayer
from pyglet.media import Player as SLPlayer


def main():
  window = pyglet.window.Window(width=1920, height=1080, resizable=True)

  imgui.create_context()
  impl = create_renderer(window)

  src = SLSource('before.mp4')
  # src = SLSource('data/debugging.mp4')#'before.mp4')

  video_player = SLPlayer()
  # manually create a square texture - this is slightly modified version of Player._create_texture
  # function, which creates a rectangle texture instead of a square one
  # video_player._texture = pyglet.image.Texture.create(src.video_format.width,
  #                                                     src.video_format.height)
  # video_player._texture = video_player._texture.get_transform(flip_y=True)
  # video_player._texture.anchor_y = 0

  # video_player.start(src)
  video_player.queue(src)
  video_player.play()


  def update(dt):
    imgui.new_frame()
    if imgui.begin_main_menu_bar():
      if imgui.is_key_pressed(imgui.KEY_RIGHT_ARROW):
        video_player.seek(video_player.time + 2.0)
      if imgui.is_key_pressed(imgui.KEY_LEFT_ARROW):
        video_player.seek(video_player.time - 2.0)
      if imgui.is_key_pressed(imgui.KEY_SPACE):
        if video_player.playing:
          video_player.pause()
        else:
          video_player.play()
      if imgui.begin_menu('File', True):
        clicked_quit, selected_quit = imgui.menu_item('Quit', 'Cmd+Q', False, True)
        if clicked_quit:
          pyglet.app.exit()
        imgui.end_menu()
      imgui.end_main_menu_bar()

  def draw(dt):
    update(dt)
    window.clear()

    # show_test_window()
    imgui.begin('test')

    imgui.text('this is a test')
    video_texture = video_player.texture
    if video_texture is not None:
      texture_ar = video_texture.width / video_texture.height
      canvas_size = imgui.get_content_region_available()
      image_width = min(canvas_size.x, canvas_size.y * texture_ar)
      image_height = image_width / texture_ar

      imgui.image(texture_id=video_texture.id,
                  width=image_width,
                  height=image_height,
                  uv0=(0, 0),
                  uv1=((video_texture.width / video_texture.owner.width),
                      (video_texture.height / video_texture.owner.height)))

    imgui.end()

    imgui.render()
    impl.render(imgui.get_draw_data())

  pyglet.clock.schedule_interval(draw, 1 / 60)
  pyglet.app.run()
  video_player.delete()
  impl.shutdown()


if __name__ == '__main__':
  main()
