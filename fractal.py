import glfw
import moderngl
import numpy as np
import time
from PIL import Image, ImageDraw, ImageFont

# Глобальные переменные
fullscreen = False
show_fps = False
windowed_size = (800, 600)
windowed_pos = (100, 100)
window = None

last_fps_time = time.time()
fps_counter = 0
current_fps = 0
fps_texture = None

# Шрифт
try:
    font = ImageFont.truetype("arial.ttf", 24)
except:
    font = ImageFont.load_default()

# Обработка клавиш
def key_callback(win, key, scancode, action, mods):
    global fullscreen, windowed_size, windowed_pos, window, show_fps
    if key == glfw.KEY_ESCAPE and action == glfw.PRESS:
        glfw.set_window_should_close(window, True)
    elif key == glfw.KEY_S and action == glfw.PRESS:
        show_fps = not show_fps
    elif key == glfw.KEY_F and action == glfw.PRESS:
        monitor = glfw.get_primary_monitor()
        mode = glfw.get_video_mode(monitor)
        if not fullscreen:
            windowed_pos = glfw.get_window_pos(window)
            windowed_size = glfw.get_window_size(window)
            glfw.set_window_monitor(window, monitor, 0, 0, mode.size.width, mode.size.height, mode.refresh_rate)
            glfw.set_input_mode(window, glfw.CURSOR, glfw.CURSOR_DISABLED)
            fullscreen = True
        else:
            glfw.set_window_monitor(window, None, *windowed_pos, *windowed_size, 0)
            glfw.set_input_mode(window, glfw.CURSOR, glfw.CURSOR_NORMAL)
            fullscreen = False

# Инициализация GLFW и контекста
glfw.init()
window = glfw.create_window(800, 600, "Mandelbrot", None, None)
glfw.make_context_current(window)
glfw.set_key_callback(window, key_callback)

ctx = moderngl.create_context()
ctx.enable(moderngl.BLEND)  # Для прозрачности текста

# Шейдер Mandelbrot
prog = ctx.program(
    vertex_shader='''
        #version 330
        in vec2 in_pos;
        out vec2 v_pos;
        void main() {
            v_pos = in_pos;
            gl_Position = vec4(in_pos, 0.0, 1.0);
        }
    ''',
    fragment_shader='''
        #version 330
        in vec2 v_pos;
        out vec4 fragColor;
        uniform vec2 center;
        uniform float zoom;
        uniform float aspect_ratio;
        uniform int max_iter;
        uniform vec3 base_color;
        void main() {
            vec2 uv = v_pos;
            uv.x *= aspect_ratio;
            vec2 c = uv * zoom + center;
            vec2 z = vec2(0.0);
            int i;
            for (i = 0; i < max_iter; i++) {
                if (dot(z, z) > 4.0) break;
                z = vec2(z.x*z.x - z.y*z.y, 2.0*z.x*z.y) + c;
            }
            float t = float(i) / float(max_iter);
            fragColor = vec4(base_color * t, 1.0);
        }
    '''
)

# Прямоугольник на весь экран
quad = np.array([
    -1.0, -1.0,
     1.0, -1.0,
    -1.0,  1.0,
    -1.0,  1.0,
     1.0, -1.0,
     1.0,  1.0
], dtype='f4')
vbo = ctx.buffer(quad.tobytes())
vao = ctx.simple_vertex_array(prog, vbo, 'in_pos')

# Шейдер и VAO для текста
text_prog = ctx.program(
    vertex_shader='''
        #version 330
        in vec2 in_pos;
        in vec2 in_uv;
        out vec2 uv;
        void main() {
            uv = in_uv;
            gl_Position = vec4(in_pos, 0.0, 1.0);
        }
    ''',
    fragment_shader='''
        #version 330
        uniform sampler2D tex;
        in vec2 uv;
        out vec4 fragColor;
        void main() {
            fragColor = texture(tex, uv);
        }
    '''
)

# Буфер и VAO для overlay, будет перезаписываться каждый кадр
overlay_vbo = ctx.buffer(reserve=6 * 4 * 4)  # 6 вершин, 4 float (x, y, u, v)
overlay_vao = ctx.vertex_array(
    text_prog,
    [(overlay_vbo, '2f 2f', 'in_pos', 'in_uv')]
)

start_time = time.time()

while not glfw.window_should_close(window):
    glfw.poll_events()
    width, height = glfw.get_framebuffer_size(window)
    ctx.viewport = (0, 0, width, height)
    ctx.clear()

    # Анимация фрактала
    t = time.time() - start_time
    zoom = 0.5 + 0.25 * np.sin(t * 0.5)
    offset_x = -0.5 + 0.3 * np.cos(t * 0.2)
    offset_y =  0.0 + 0.3 * np.sin(t * 0.3)
    aspect_ratio = width / height
    color = [
        0.5 + 0.5 * np.sin(t * 0.7),
        0.5 + 0.5 * np.sin(t * 0.9 + 2),
        0.5 + 0.5 * np.sin(t * 1.1 + 4),
    ]
    prog['center'].value = (offset_x, offset_y)
    prog['zoom'].value = zoom
    prog['aspect_ratio'].value = aspect_ratio
    prog['max_iter'].value = 300
    prog['base_color'].value = tuple(color)
    vao.render()

    # Обновляем FPS
    fps_counter += 1
    now = time.time()
    if now - last_fps_time >= 1.0:
        current_fps = fps_counter
        fps_counter = 0
        last_fps_time = now
        if show_fps:
            img = Image.new('RGBA', (256, 64), color=(0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.text((10, 10), f"FPS: {current_fps}", font=font, fill=(255, 255, 255, 255))
            img = img.transpose(Image.FLIP_TOP_BOTTOM)
            fps_texture = ctx.texture(img.size, 4, img.tobytes())
            fps_texture.filter = (moderngl.NEAREST, moderngl.NEAREST)

    # Отображаем FPS-оверлей
    if show_fps and fps_texture:
        # Размер текста в пикселях
        ow, oh = 256, 64

        # В OpenGL-координаты
        x0 = -1.0
        x1 = -1.0 + 2.0 * ow / width
        y0 = 1.0
        y1 = 1.0 - 2.0 * oh / height

        overlay_quad = np.array([
            x0, y0, 0.0, 1.0,
            x1, y0, 1.0, 1.0,
            x0, y1, 0.0, 0.0,
            x0, y1, 0.0, 0.0,
            x1, y0, 1.0, 1.0,
            x1, y1, 1.0, 0.0,
        ], dtype='f4')
        overlay_vbo.write(overlay_quad.tobytes())
        fps_texture.use(location=0)
        text_prog['tex'].value = 0
        overlay_vao.render()

    glfw.swap_buffers(window)

glfw.terminate()
