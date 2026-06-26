from pathlib import Path

class MediaType:
    TEXT, IMAGE, AUDIO, VIDEO, DOCUMENT, CODE, BINARY = "text", "image", "audio", "video", "document", "code", "binary"
    EXTENSIONS = {
        IMAGE: {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg', '.webp'},
        AUDIO: {'.mp3', '.wav', '.ogg', '.flac', '.aac', '.m4a'},
        VIDEO: {'.mp4', '.avi', '.mov', '.mkv', '.webm'},
        DOCUMENT: {'.pdf', '.doc', '.docx', '.odt', '.rtf', '.txt', '.md'},
        CODE: {'.py', '.js', '.html', '.css', '.json', '.xml', '.yaml', '.sh'},
    }
    @classmethod
    def from_filename(cls, filename):
        ext = Path(filename).suffix.lower()
        for media_type, extensions in cls.EXTENSIONS.items():
            if ext in extensions: return media_type
        return cls.BINARY
