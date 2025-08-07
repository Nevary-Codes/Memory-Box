from cloudinary.utils import cloudinary_url

def get_watermarked_url(image_url):
    from urllib.parse import quote
    watermark_text = "MemoryBox"
    encoded_text = quote(watermark_text)

    transformation = (
        "l_text:Arial_80_bold:" + encoded_text +  # Bigger & Bold font
        ",co_rgb:FFFFFF,"  # White color
        "g_center,"        # Center position
        "o_50"             # 50% opacity (more visible than 30)
    )

    return image_url.replace("/upload/", f"/upload/{transformation}/")