"""
Subtitle Utilities - Comprehensive subtitle helper functions
Complete implementation for subtitle detection, parsing, and management
"""

import os
import re
import chardet
from datetime import timedelta

# Import constants safely
try:
    from ..constants import VIDEO_EXTENSIONS
except ImportError:
    # Fallback video extensions
    VIDEO_EXTENSIONS = ['.mp4', '.mkv', '.avi', '.ts', '.m2ts', '.mov', '.m4v']

def detect_subtitle_encoding(file_path, sample_size=10000):
    """
    Detect subtitle file encoding with multiple fallbacks
    
    Args:
        file_path: Path to subtitle file
        sample_size: Number of bytes to read for detection
    
    Returns:
        str: Detected encoding (utf-8, latin-1, cp1256, etc.)
    """
    if not os.path.exists(file_path):
        return 'utf-8'
    
    try:
        # Read sample for detection
        with open(file_path, 'rb') as f:
            raw_data = f.read(min(os.path.getsize(file_path), sample_size))
        
        if not raw_data:
            return 'utf-8'
        
        # Use chardet for primary detection
        result = chardet.detect(raw_data)
        detected_encoding = result['encoding']
        confidence = result['confidence']
        
        # Map common encodings
        encoding_map = {
            'ascii': 'utf-8',
            'iso-8859-1': 'latin-1',
            'iso-8859-6': 'cp1256',
            'windows-1251': 'cp1251',
            'windows-1252': 'cp1252',
            'windows-1256': 'cp1256',
            'gb2312': 'gbk',
            'big5': 'big5',
        }
        
        # Use mapping if available
        if detected_encoding and detected_encoding.lower() in encoding_map:
            return encoding_map[detected_encoding.lower()]
        
        # Return detected encoding or default
        return detected_encoding or 'utf-8'
        
    except Exception as e:
        # Fallback to common encodings
        return 'utf-8'

def get_matching_subtitle_files(video_path, search_recursive=False):
    """
    Find all matching subtitle files for a video
    
    Args:
        video_path: Path to video file
        search_recursive: Search in subdirectories
    
    Returns:
        list: List of matching subtitle file paths
    """
    if not video_path or not os.path.exists(video_path):
        return []
    
    video_dir = os.path.dirname(video_path)
    video_name = os.path.splitext(os.path.basename(video_path))[0]
    
    subtitle_files = []
    subtitle_extensions = ['.srt', '.sub', '.ass', '.ssa', '.vtt']
    
    # Clean video name for matching
    clean_video_name = _clean_filename_for_matching(video_name)
    
    def search_in_directory(search_dir):
        """Search for subtitles in a directory"""
        found = []
        
        for file in os.listdir(search_dir):
            file_path = os.path.join(search_dir, file)
            
            # Skip directories unless recursive
            if os.path.isdir(file_path):
                if search_recursive:
                    found.extend(search_in_directory(file_path))
                continue
            
            # Check if it's a subtitle file
            file_lower = file.lower()
            if any(file_lower.endswith(ext) for ext in subtitle_extensions):
                # Check for matches
                if _is_subtitle_match(file, clean_video_name):
                    found.append(file_path)
        
        return found
    
    # Search in video directory
    subtitle_files.extend(search_in_directory(video_dir))
    
    # Also check in a "Subs" or "subtitles" subdirectory
    possible_sub_dirs = ['Subs', 'subs', 'Subtitles', 'subtitles', 'Sub']
    for sub_dir in possible_sub_dirs:
        sub_dir_path = os.path.join(video_dir, sub_dir)
        if os.path.isdir(sub_dir_path):
            subtitle_files.extend(search_in_directory(sub_dir_path))
    
    # Sort by relevance (exact matches first, then language matches)
    subtitle_files = _sort_subtitles_by_relevance(subtitle_files, clean_video_name)
    
    return subtitle_files

def _clean_filename_for_matching(filename):
    """Clean filename for subtitle matching"""
    # Remove common release groups, quality markers, etc.
    patterns_to_remove = [
        r'\[.*?\]', r'\(.*?\)',  # Remove brackets and parentheses
        r'\d{3,4}p',             # Remove resolution (720p, 1080p)
        r'\.HD\.', r'\.SD\.',    # Remove quality markers
        r'\.x264', r'\.x265',    # Remove codec info
        r'\.AAC\.', r'\.AC3\.',  # Remove audio codec
        r'\.WEB-?DL', r'\.BLU-?RAY',  # Remove source info
        r'\.DTS\.', r'\.DD5\.1', # Remove audio formats
        r'\.EXTENDED', r'\.UNCUT', # Remove edition info
        r'\.REPACK', r'\.PROPER', # Remove release info
    ]
    
    cleaned = filename
    for pattern in patterns_to_remove:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    
    # Remove multiple dots and trim
    cleaned = re.sub(r'\.+', '.', cleaned)
    cleaned = cleaned.strip(' ._-')
    
    return cleaned.lower()

def _is_subtitle_match(subtitle_file, clean_video_name):
    """Check if subtitle file matches video"""
    subtitle_name = os.path.splitext(subtitle_file)[0]
    subtitle_clean = _clean_filename_for_matching(subtitle_name)
    
    # Exact match
    if clean_video_name == subtitle_clean:
        return True
    
    # Video name contained in subtitle name
    if clean_video_name in subtitle_clean:
        return True
    
    # Check for language variations
    # Remove language codes and check again
    lang_pattern = r'\.(en|ar|fr|es|de|it|ru|tr|fa|he|zh|ja|ko)(\.|$)'
    subtitle_without_lang = re.sub(lang_pattern, '', subtitle_clean, flags=re.IGNORECASE)
    
    if clean_video_name == subtitle_without_lang:
        return True
    
    return False

def _sort_subtitles_by_relevance(subtitle_files, clean_video_name):
    """Sort subtitle files by relevance to video"""
    def relevance_score(file_path):
        filename = os.path.splitext(os.path.basename(file_path))[0]
        filename_clean = _clean_filename_for_matching(filename)
        
        score = 0
        
        # Exact match gets highest score
        if clean_video_name == filename_clean:
            score += 100
        
        # Contains video name
        if clean_video_name in filename_clean:
            score += 50
        
        # Language preference (English gets bonus)
        if '.en.' in filename.lower() or filename.lower().endswith('.en'):
            score += 20
        
        # File size (reasonable size gets bonus)
        try:
            size = os.path.getsize(file_path)
            if 1024 < size < 1024 * 1024:  # Between 1KB and 1MB
                score += 10
        except:
            pass
        
        # SRT format preferred
        if file_path.lower().endswith('.srt'):
            score += 5
        
        return score
    
    return sorted(subtitle_files, key=relevance_score, reverse=True)

def parse_subtitle_language(filename):
    """
    Parse language from subtitle filename with comprehensive detection
    
    Args:
        filename: Subtitle filename
    
    Returns:
        str: Detected language name
    """
    filename_lower = filename.lower()
    
    # Comprehensive language patterns
    language_patterns = {
        'Arabic': ['arabic', 'ara', '.ar.', 'arab', 'العربية', 'ara_', '_ara'],
        'English': ['english', 'eng', '.en.', 'en_', '_en', 'eng_', '_eng'],
        'French': ['french', 'fre', '.fr.', 'fr_', '_fr', 'fre_', '_fre'],
        'Spanish': ['spanish', 'spa', '.es.', 'es_', '_es', 'spa_', '_spa'],
        'German': ['german', 'ger', '.de.', 'de_', '_de', 'ger_', '_ger'],
        'Italian': ['italian', 'ita', '.it.', 'it_', '_it', 'ita_', '_ita'],
        'Russian': ['russian', 'rus', '.ru.', 'ru_', '_ru', 'rus_', '_rus'],
        'Turkish': ['turkish', 'tur', '.tr.', 'tr_', '_tr', 'tur_', '_tur'],
        'Persian': ['persian', 'per', '.fa.', 'fa_', '_fa', 'pers_', '_pers', 'فارسی'],
        'Hebrew': ['hebrew', 'heb', '.he.', 'he_', '_he', 'heb_', '_heb', 'עברית'],
        'Chinese': ['chinese', 'chi', '.zh.', 'zh_', '_zh', '.cn.', 'chi_', '中文'],
        'Japanese': ['japanese', 'jpn', '.ja.', 'ja_', '_ja', 'jpn_', '日本語'],
        'Korean': ['korean', 'kor', '.ko.', 'ko_', '_ko', 'kor_', '한국어'],
        'Portuguese': ['portuguese', 'por', '.pt.', 'pt_', '_pt', 'por_'],
        'Dutch': ['dutch', 'dut', '.nl.', 'nl_', '_nl', 'dut_'],
        'Greek': ['greek', 'gre', '.el.', 'el_', '_el', 'gre_'],
        'Hindi': ['hindi', 'hin', '.hi.', 'hi_', '_hi', 'hin_', 'हिन्दी'],
        'Urdu': ['urdu', 'urd', '.ur.', 'ur_', '_ur', 'urd_', 'اردو'],
        'Bengali': ['bengali', 'ben', '.bn.', 'bn_', '_bn', 'ben_'],
        'Tamil': ['tamil', 'tam', '.ta.', 'ta_', '_ta', 'tam_'],
        'Thai': ['thai', 'tha', '.th.', 'th_', '_th', 'tha_'],
    }
    
    # Check for language patterns
    for language, patterns in language_patterns.items():
        for pattern in patterns:
            if pattern in filename_lower:
                return language
    
    # Check ISO 639-1 and 639-2 codes
    iso_codes = {
        'ar': 'Arabic', 'en': 'English', 'fr': 'French',
        'es': 'Spanish', 'de': 'German', 'it': 'Italian',
        'ru': 'Russian', 'tr': 'Turkish', 'fa': 'Persian',
        'he': 'Hebrew', 'zh': 'Chinese', 'ja': 'Japanese',
        'ko': 'Korean', 'pt': 'Portuguese', 'nl': 'Dutch',
        'el': 'Greek', 'hi': 'Hindi', 'ur': 'Urdu',
        'bn': 'Bengali', 'ta': 'Tamil', 'th': 'Thai',
        'sv': 'Swedish', 'no': 'Norwegian', 'da': 'Danish',
        'fi': 'Finnish', 'pl': 'Polish', 'cs': 'Czech',
        'sk': 'Slovak', 'hu': 'Hungarian', 'ro': 'Romanian',
    }
    
    for code, language in iso_codes.items():
        pattern = f".{code}."
        if pattern in filename_lower:
            return language
    
    return 'Unknown'

def validate_subtitle_file(file_path):
    """
    Validate subtitle file integrity and format
    
    Args:
        file_path: Path to subtitle file
    
    Returns:
        tuple: (is_valid, message, format_type)
    """
    if not os.path.exists(file_path):
        return False, "File does not exist", None
    
    try:
        size = os.path.getsize(file_path)
        if size == 0:
            return False, "File is empty", None
        
        if size > 10 * 1024 * 1024:  # 10MB
            return False, "File too large (max 10MB)", None
        
        # Try to read with multiple encodings
        encodings = ['utf-8', 'latin-1', 'cp1256', 'cp1252', 'utf-16']
        
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    content = f.read(5000)  # Read first 5KB
                
                format_type = detect_subtitle_format(content)
                
                if format_type:
                    # Basic content validation
                    lines = content.split('\n')
                    if len(lines) < 2:
                        return False, "Not enough content", format_type
                    
                    return True, f"Valid {format_type.upper()} file ({encoding})", format_type
                    
            except UnicodeDecodeError:
                continue
        
        return False, "Cannot decode with any supported encoding", None
        
    except Exception as e:
        return False, f"Error: {str(e)[:50]}", None

def detect_subtitle_format(content):
    """Detect subtitle format from content"""
    content_lower = content.lower()
    
    # Check for SRT format
    if re.search(r'\d+\s*\n\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,.]\d{3}', content):
        return 'srt'
    
    # Check for ASS/SSA format
    if '[script info]' in content_lower or '[v4+ styles]' in content_lower:
        return 'ass'
    if '[events]' in content_lower and 'format:' in content_lower:
        return 'ssa'
    
    # Check for MicroDVD format
    if re.search(r'^\{\d+\}\{\d+\}', content, re.MULTILINE):
        return 'sub'
    
    # Check for WebVTT format
    if 'webvtt' in content_lower:
        return 'vtt'
    
    # Check for simple timestamp format
    if re.search(r'\d{1,2}:\d{2}:\d{2}[,.]\d{3}\s+.+', content):
        return 'txt'
    
    return None

def is_subtitle_content(content, min_lines=3):
    """
    Check if content looks like subtitle data
    
    Args:
        content: Text content to check
        min_lines: Minimum number of valid subtitle lines
    
    Returns:
        bool: True if content appears to be subtitles
    """
    if not content or len(content.strip()) < 20:
        return False
    
    lines = content.split('\n')
    subtitle_line_count = 0
    
    # Check for common subtitle patterns
    for line in lines[:50]:  # Check first 50 lines
        line = line.strip()
        if not line:
            continue
        
        # Check for SRT timestamp pattern
        if re.search(r'\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,.]\d{3}', line):
            subtitle_line_count += 1
        
        # Check for MicroDVD pattern
        elif re.search(r'^\{\d+\}\{\d+\}', line):
            subtitle_line_count += 1
        
        # Check for simple timestamp
        elif re.search(r'\d{1,2}:\d{2}:\d{2}[,.]\d{3}\s+.+', line):
            subtitle_line_count += 1
        
        if subtitle_line_count >= min_lines:
            return True
    
    return False

def get_video_for_subtitle(subtitle_path):
    """
    Find matching video file for subtitle
    
    Args:
        subtitle_path: Path to subtitle file
    
    Returns:
        str or None: Path to matching video file
    """
    if not subtitle_path or not os.path.exists(subtitle_path):
        return None
    
    subtitle_dir = os.path.dirname(subtitle_path)
    subtitle_name = os.path.splitext(os.path.basename(subtitle_path))[0]
    
    # Clean subtitle name
    clean_sub_name = _clean_filename_for_matching(subtitle_name)
    
    # Remove language suffix
    lang_pattern = r'\.(en|ar|fr|es|de|it|ru|tr|fa|he|zh|ja|ko)$'
    clean_sub_name = re.sub(lang_pattern, '', clean_sub_name, flags=re.IGNORECASE)
    
    # Search for video files
    for file in os.listdir(subtitle_dir):
        file_path = os.path.join(subtitle_dir, file)
        
        if os.path.isdir(file_path):
            continue
        
        # Check if it's a video file
        ext = os.path.splitext(file)[1].lower()
        if ext in VIDEO_EXTENSIONS:
            video_name = os.path.splitext(file)[0]
            clean_video_name = _clean_filename_for_matching(video_name)
            
            # Check for match
            if clean_sub_name == clean_video_name:
                return file_path
            
            # Check if subtitle name is in video name
            if clean_sub_name in clean_video_name:
                return file_path
    
    return None

def clean_subtitle_text(text):
    """
    Clean subtitle text by removing formatting tags and normalizing
    
    Args:
        text: Subtitle text to clean
    
    Returns:
        str: Cleaned subtitle text
    """
    if not text:
        return ""
    
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    
    # Remove ASS/SSA formatting tags
    text = re.sub(r'\{[^}]*\}', '', text)
    
    # Replace special newline markers
    text = text.replace('\\N', '\n').replace('\\n', '\n').replace('\\h', ' ')
    
    # Remove multiple spaces
    text = re.sub(r'\s+', ' ', text)
    
    # Trim
    text = text.strip()
    
    return text

def calculate_subtitle_stats(subtitle_lines):
    """
    Calculate statistics for subtitle lines
    
    Args:
        subtitle_lines: List of subtitle line dictionaries
    
    Returns:
        dict: Statistics dictionary
    """
    if not subtitle_lines:
        return {}
    
    total_lines = len(subtitle_lines)
    total_chars = sum(len(line.get('text', '')) for line in subtitle_lines)
    total_words = sum(len(line.get('text', '').split()) for line in subtitle_lines)
    
    # Calculate duration
    if subtitle_lines:
        first_line = subtitle_lines[0]
        last_line = subtitle_lines[-1]
        
        start_ms = first_line.get('start_ms', 0)
        end_ms = last_line.get('end_ms', 0)
        duration_ms = max(0, end_ms - start_ms)
        duration_sec = duration_ms / 1000.0
    else:
        duration_sec = 0
    
    # Calculate reading speed
    if duration_sec > 0:
        words_per_minute = (total_words / duration_sec) * 60
        chars_per_second = total_chars / duration_sec
    else:
        words_per_minute = 0
        chars_per_second = 0
    
    # Average line duration
    avg_line_duration = duration_ms / total_lines if total_lines > 0 else 0
    
    # Language detection (simple)
    sample_text = ' '.join(line.get('text', '')[:100] for line in subtitle_lines[:5])
    detected_lang = detect_language_from_text(sample_text)
    
    return {
        'total_lines': total_lines,
        'total_chars': total_chars,
        'total_words': total_words,
        'duration_seconds': duration_sec,
        'duration_formatted': format_duration(duration_sec),
        'words_per_minute': round(words_per_minute, 1),
        'chars_per_second': round(chars_per_second, 1),
        'avg_line_duration_ms': round(avg_line_duration, 1),
        'detected_language': detected_lang,
        'reading_difficulty': assess_reading_difficulty(words_per_minute),
    }

def detect_language_from_text(text):
    """Simple language detection from text"""
    if not text:
        return 'Unknown'
    
    # Very simple detection based on character sets
    text_lower = text.lower()
    
    # Arabic range
    if re.search(r'[\u0600-\u06FF]', text):
        return 'Arabic'
    
    # Hebrew range
    if re.search(r'[\u0590-\u05FF]', text):
        return 'Hebrew'
    
    # Persian additional characters
    if re.search(r'[\uFB8A\u067E\u0686\u06AF]', text):
        return 'Persian'
    
    # Common English words
    english_words = ['the', 'and', 'you', 'that', 'have', 'for', 'not', 'with']
    english_count = sum(1 for word in english_words if word in text_lower)
    
    if english_count >= 3:
        return 'English'
    
    return 'Unknown'

def assess_reading_difficulty(wpm):
    """Assess reading difficulty based on words per minute"""
    if wpm < 100:
        return 'Easy'
    elif wpm < 150:
        return 'Moderate'
    elif wpm < 200:
        return 'Fast'
    else:
        return 'Very Fast'

def format_duration(seconds):
    """Format duration in seconds to readable string"""
    try:
        seconds = int(seconds)
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        
        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"
    except:
        return "0s"

def convert_subtitle_format(content, from_format, to_format):
    """
    Convert subtitle content between formats
    
    Args:
        content: Subtitle content
        from_format: Source format ('srt', 'ass', 'sub', 'vtt')
        to_format: Target format ('srt', 'ass', 'sub', 'vtt')
    
    Returns:
        str: Converted subtitle content
    """
    # This is a simplified converter
    # For production, you'd want a more robust implementation
    
    if from_format == to_format:
        return content
    
    # Parse lines based on source format
    lines = []
    
    if from_format == 'srt':
        # Parse SRT format
        blocks = re.split(r'\n\s*\n', content.strip())
        for block in blocks:
            block_lines = block.strip().split('\n')
            if len(block_lines) >= 3:
                time_match = re.search(
                    r'(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})',
                    block_lines[1]
                )
                if time_match:
                    start = time_match.group(1).replace('.', ',')
                    end = time_match.group(2).replace('.', ',')
                    text = ' '.join(block_lines[2:])
                    lines.append({'start': start, 'end': end, 'text': text})
    
    # Convert to target format
    if to_format == 'srt':
        result = []
        for i, line in enumerate(lines, 1):
            result.append(f"{i}")
            result.append(f"{line['start']} --> {line['end']}")
            result.append(line['text'])
            result.append("")
        return '\n'.join(result)
    
    elif to_format == 'vtt':
        result = ["WEBVTT", ""]
        for line in lines:
            result.append(f"{line['start'].replace(',', '.')} --> {line['end'].replace(',', '.')}")
            result.append(line['text'])
            result.append("")
        return '\n'.join(result)
    
    # Return original if conversion not implemented
    return content