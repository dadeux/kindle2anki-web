import requests
import hashlib
import os
from pathlib import Path
from typing import Optional, Tuple
import time
import io
from requests.exceptions import RequestException
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any

# Setup logging (always needed)
logger = logging.getLogger(__name__)

@dataclass
class CoverResult:
   """Structured result for book cover fetches."""
   image_bytes: Optional[bytes]
   source: str  # e.g., "openlibrary", "google", "cache", "placeholder"
   url: str     # Source URL where the image came from
   metadata: Dict[str, Any] = None  # Additional info like size, format

   def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

   @property
   def success(self) -> bool:
       """Check if a cover was successfully fetched."""
       return self.image_bytes is not None and len(self.image_bytes) > 0
   
   def to_dict(self) -> Dict[str, Any]:
       """Convert to dictionary for serialization."""
       return {
           "source": self.source,
           "url": self.url,
           "success": self.success,
           "size_bytes": len(self.image_bytes) if self.image_bytes else 0,
           "metadata": self.metadata or {}
       } 

class BookCoverFetcher:
    """
    Fetch book covers from multiple sources with caching.
    """
    
    def __init__(self, cache_dir: str = "./covers", user_agent: str = None):
        """
        Initialize the fetcher with cache directory.
        
        Args:
            cache_dir: Directory to cache downloaded covers
            user_agent: Custom User-Agent for requests
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        
        self.user_agent = user_agent or (
            "Mozilla/5.0 (compatible; Kindle2AnkiApp/1.0; +http://yourdomain.com)"
        )
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent})
        
        # Priority of sources (highest first)
        self.sources = [
            self._fetch_openlibrary,
            self._fetch_google_books,
            self._fetch_amazon_direct
        ]
    

        def _check_cache(self, isbn, title, author, size) -> CoverResult:
            """Check cache - returns CoverResult."""
            cache_key = self._create_cache_key(isbn, title, author, size)
            cache_file = self.cache_dir / f"{cache_key}.jpg"
            
            if not cache_file.exists():
                return CoverResult(None, "cache", "", {"cache_hit": False})
            
            try:
                with open(cache_file, "rb") as f:
                    image_bytes = f.read()
                
                return CoverResult(
                    image_bytes,
                    "cache",
                    f"file://{cache_file}",
                    {
                        "cache_hit": True,
                        "cache_key": cache_key,
                        "size_bytes": len(image_bytes),
                        "cached_at": cache_file.stat().st_mtime
                    }
                )
            except Exception as e:
                return CoverResult(None, "cache", "", {"error": str(e), "cache_hit": False})

    def get_cover(
        self, 
        isbn: str = None, 
        title: str = None, 
        author: str = None,
        size: str = "M",
        use_cache: bool = True
        ) -> CoverResult:
        """
        Get book cover image from best available source.
        
        Args:
            isbn: ISBN-10 or ISBN-13 (preferred)
            title: Book title
            author: Book author
            size: Image size - 'S' (small), 'M' (medium), 'L' (large)
            use_cache: Use cached image if available
            
        Returns:
            CoverResult object with image bytes and metadata
        """
        # 1. Check cache (returns CoverResult)
        if use_cache:
            cache_result = self._check_cache(isbn, title, author, size)
            if cache_result.success:
                # print("Cache hit")
                return cache_result
        
        # 2. Try sources (all return CoverResult)
        for source_func in self.sources:
            result = source_func(isbn, title, author, size)
            if result.success:
                # Cache the successful result
                self._save_to_cache(result, isbn, title, author, size)
                return result
        
        # 3. Fallback placeholder (returns CoverResult)
        placeholder_bytes = self._get_placeholder(title, author, size)
        return CoverResult(
            image_bytes=placeholder_bytes,
            source="placeholder",
            url="",
            metadata={
                "is_placeholder": True,
                "title": title,
                "author": author,
                "size": size,
                "reason": "All sources failed - using placeholder"
            }
        )
    
    def _save_to_cache(self, result, isbn, title, author, size):
        """Save successful result to cache."""
        print("Caching cover")
        if not result.success:
            return
        
        cache_key = self._create_cache_key(isbn, title, author, size)
        cache_file = self.cache_dir / f"{cache_key}.jpg"
        
        try:
            with open(cache_file, "wb") as f:
                f.write(result.image_bytes)
        except Exception as e:
            print(f"Failed to cache: {e}")
    
    def _create_cache_key(self, isbn, title, author, size):
        key_str = f"{isbn or ''}_{title or ''}_{author or ''}_{size}"
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def _check_cache(self, isbn, title, author, size) -> CoverResult:
        """
        Check if cover is in cache - returns CoverResult.
        
        Args:
            isbn: ISBN of the book
            title: Title of the book  
            author: Author of the book
            size: Requested image size
        
        Returns:
            CoverResult object (successful if found in cache, failed otherwise)
        """
        print("Checking cache...")
        try:
            # Generate cache filename
            cache_file = self._get_cache_filename(isbn, title, author, size)
            
            # Check if file exists
            if not cache_file.exists():
                return CoverResult(
                    image_bytes=None,
                    source="cache",
                    url="",
                    metadata={
                        "cache_hit": False,
                        "cache_file": str(cache_file),
                        "reason": "File does not exist",
                        "isbn": isbn,
                        "title": title
                    }
                )
            
            # Check file size (empty cache files shouldn't happen, but guard against it)
            file_size = cache_file.stat().st_size
            if file_size == 0:
                # Remove corrupted cache file
                cache_file.unlink(missing_ok=True)
                return CoverResult(
                    image_bytes=None,
                    source="cache",
                    url="",
                    metadata={
                        "cache_hit": False,
                        "cache_file": str(cache_file),
                        "reason": "Empty file removed",
                        "isbn": isbn
                    }
                )
            
            # Read the cached image
            with open(cache_file, "rb") as f:
                image_bytes = f.read()
            
            # Verify we actually read something
            if not image_bytes:
                return CoverResult(
                    image_bytes=None,
                    source="cache",
                    url="",
                    metadata={
                        "cache_hit": False,
                        "cache_file": str(cache_file),
                        "reason": "Read empty bytes",
                        "isbn": isbn
                    }
                )
            
            # Success - cached cover found
            return CoverResult(
                image_bytes=image_bytes,
                source="cache",
                url=f"file://{cache_file.absolute()}",
                metadata={
                    "cache_hit": True,
                    "cache_file": str(cache_file),
                    "size_bytes": len(image_bytes),
                    "file_size": file_size,
                    "cached_at": cache_file.stat().st_mtime,
                    "isbn": isbn,
                    "title": title,
                    "author": author,
                    "size": size
                }
            )
            
        except PermissionError as e:
            return CoverResult(
                image_bytes=None,
                source="cache", 
                url="",
                metadata={
                    "cache_hit": False,
                    "error": "permission_error",
                    "exception": type(e).__name__,
                    "message": str(e),
                    "isbn": isbn,
                    "reason": f"Cannot read cache file: {e}"
                }
            )
            
        except Exception as e:
            return CoverResult(
                image_bytes=None,
                source="cache",
                url="",
                metadata={
                    "cache_hit": False,
                    "error": "unexpected_error",
                    "exception": type(e).__name__,
                    "message": str(e),
                    "isbn": isbn,
                    "reason": f"Unexpected error checking cache: {e}"
                }
            )

    def _get_cache_filename(self, isbn, title, author, size):
        """Should return a hash-based filename."""
        cache_key = self._create_cache_key(isbn, title, author, size)
        return self.cache_dir / f"{cache_key}.jpg"  # Should be just the hash!

    def _get_placeholder(self, title=None, author=None, size="S"):
        """
        Generate a proper placeholder image with text.
        
        Args:
            title: Book title to display
            author: Book author to display  
            size: Image size - determines dimensions
        
        Returns:
            bytes of a valid JPEG/PNG image
        """
        try:
            # Import PIL locally since it's optional
            from PIL import Image, ImageDraw, ImageFont
            import io
            
            # Set dimensions based on size
            size_map = {"S": (150, 200), "M": (300, 400), "L": (600, 800)}
            width, height = size_map.get(size, (300, 400))
            
            # Create image with a neutral background
            img = Image.new('RGB', (width, height), color=(240, 240, 240))
            draw = ImageDraw.Draw(img)
            
            # Add a subtle border
            draw.rectangle([0, 0, width-1, height-1], outline=(200, 200, 200), width=2)
            
            # Try to load a font, fallback to default
            try:
                # Try common font paths
                font_paths = [
                    "/System/Library/Fonts/Helvetica.ttc",  # macOS
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Linux
                    "C:/Windows/Fonts/arial.ttf",  # Windows
                ]
                
                font = None
                for path in font_paths:
                    try:
                        font = ImageFont.truetype(path, size=24)
                        break
                    except:
                        continue
                
                if font is None:
                    font = ImageFont.load_default()
            except:
                font = ImageFont.load_default()
            
            # Prepare text
            display_text = []
            if title:
                # Truncate long titles
                short_title = title[:30] + "..." if len(title) > 30 else title
                display_text.append(short_title)
            
            if author:
                short_author = author[:30] + "..." if len(author) > 30 else author
                display_text.append(f"by {short_author}")
            
            if not display_text:
                display_text = ["No Cover", "Available"]
            
            # Draw text with word wrapping
            y_position = height // 3
            line_height = 35
            
            for line in display_text:
                # Simple word wrapping
                words = line.split()
                lines = []
                current_line = []
                
                for word in words:
                    current_line.append(word)
                    test_line = ' '.join(current_line)
                    # Rough estimate of text width
                    if len(test_line) * 12 > width * 0.8:  # 80% of image width
                        lines.append(' '.join(current_line[:-1]))
                        current_line = [word]
                
                if current_line:
                    lines.append(' '.join(current_line))
                
                # Draw each wrapped line
                for wrapped_line in lines:
                    # Calculate text position (centered)
                    try:
                        bbox = draw.textbbox((0, 0), wrapped_line, font=font)
                        text_width = bbox[2] - bbox[0]
                        text_height = bbox[3] - bbox[1]
                    except:
                        # Fallback for old PIL versions
                        text_width = len(wrapped_line) * 12
                        text_height = 24
                    
                    x = (width - text_width) // 2
                    y = y_position
                    
                    # Draw text with shadow for readability
                    draw.text((x+1, y+1), wrapped_line, font=font, fill=(180, 180, 180))
                    draw.text((x, y), wrapped_line, font=font, fill=(80, 80, 80))
                    
                    y_position += line_height
            
            # Add "No Cover Available" at bottom
            footer = "No Cover Available"
            try:
                bbox = draw.textbbox((0, 0), footer, font=font)
                footer_width = bbox[2] - bbox[0]
            except:
                footer_width = len(footer) * 12
            
            footer_x = (width - footer_width) // 2
            footer_y = height - 50
            draw.text((footer_x, footer_y), footer, font=font, fill=(150, 150, 150))
            
            # Convert to bytes
            img_bytes = io.BytesIO()
            img.save(img_bytes, format='JPEG', quality=85)
            return img_bytes.getvalue()
            
        except Exception as e:
            # Ultimate fallback: tiny valid JPEG
            print(f"Placeholder generation failed: {e}")
            return b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xc4\x00\xb5\x10\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05\x04\x04\x00\x00\x01}\x01\x02\x03\x00\x04\x11\x05\x12!1A\x06\x13Qa\x07"q\x142\x81\x91\xa1\x08#B\xb1\xc1\x15R\xd1\xf0$3br\x82\t\n\x16\x17\x18\x19\x1a%&\'()*456789:CDEFGHIJSTUVWXYZcdefghijstuvwxyz\x83\x84\x85\x86\x87\x88\x89\x8a\x92\x93\x94\x95\x96\x97\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5\xb6\xb7\xb8\xb9\xba\xc2\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6\xd7\xd8\xd9\xda\xe1\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf1\xf2\xf3\xf4\xf5\xf6\xf7\xf8\xf9\xfa\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xec\xe8\xa2\x8a\xff\xd9'
    
    def _fetch_openlibrary(
        self, isbn, title, author, size
        ) -> CoverResult:
        """
        Fetch from Open Library Covers API.
        Highest quality for classic/known books.
        """
        if not isbn:
            return CoverResult(
                image_bytes=None,
                source="openlibrary",
                url="",
                metadata={"error": "no_isbn", "reason": "ISBN required for Open Library"}
        )
        
        # Open Library API
        url = f"https://covers.openlibrary.org/b/isbn/{isbn}-{size}.jpg"
        
        response = self.session.get(url, timeout=10)
        response.raise_for_status()
        
        # Check if it's not the default "no cover" image
        if len(response.content) < 5000:  # Default image is small
            return CoverResult(
                image_bytes=None,
                source="openlibrary",
                url=url,
                metadata={
                    "error": "default_image",
                    "size_bytes": len(response.content),
                    "isbn": isbn,
                    "note": "Image too small, likely default 'no cover'"
                }
            )
        # Success - valid cover found
        return CoverResult(
            image_bytes=response.content,
            source="openlibrary",
            url=url,
            metadata={
                "size_bytes": len(response.content),
                "content_type": response.headers.get('content-type', 'image/jpeg'),
                "isbn": isbn,
                "status_code": response.status_code,
                "fetched_at": time.time()
            }
        )
    
    def _fetch_google_books(self, isbn, title, author, size) -> CoverResult:
        """
        Fetch from Google Books API - returns CoverResult object.
        """
        # Map size to Google's naming convention
        size_map = {"S": "small", "M": "thumbnail", "L": "large"}
        google_size = size_map.get(size, "thumbnail")
        
        # Build query
        query_parts = []
        if isbn:
            query_parts.append(f"isbn:{isbn}")
        if title:
            query_parts.append(f"intitle:{title}")
        if author:
            query_parts.append(f"inauthor:{author}")
        
        # Check if we have enough to search
        if not query_parts:
            return CoverResult(
                image_bytes=None,
                source="google",
                url="",
                metadata={
                    "error": "insufficient_query",
                    "reason": "Need at least ISBN, title, or author to search",
                    "isbn": isbn,
                    "title": title,
                    "author": author
                }
            )
        
        query = "+".join(query_parts)
        api_url = f"https://www.googleapis.com/books/v1/volumes?q={query}"
        
        try:
            # Make API request
            response = self.session.get(api_url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            # Check if any books found
            if data.get("totalItems", 0) == 0:
                return CoverResult(
                    image_bytes=None,
                    source="google",
                    url=api_url,
                    metadata={
                        "error": "no_results",
                        "query": query,
                        "total_items": 0,
                        "isbn": isbn
                    }
                )
            
            # Get first result
            volume = data["items"][0]
            volume_info = volume.get("volumeInfo", {})
            
            # Check for image links
            image_links = volume_info.get("imageLinks", {})
            image_url = image_links.get(google_size)
            
            if not image_url:
                # Book found but no cover image
                return CoverResult(
                    image_bytes=None,
                    source="google",
                    url=api_url,
                    metadata={
                        "error": "no_cover_image",
                        "query": query,
                        "total_items": data.get("totalItems", 0),
                        "title": volume_info.get("title"),
                        "available_sizes": list(image_links.keys()),
                        "requested_size": google_size
                    }
                )
            
            # Fetch the actual cover image
            img_response = self.session.get(image_url, timeout=10)
            img_response.raise_for_status()
            
            # Success - return with rich metadata
            return CoverResult(
                image_bytes=img_response.content,
                source="google",
                url=image_url,
                metadata={
                    "size_bytes": len(img_response.content),
                    "content_type": img_response.headers.get('content-type', 'image/jpeg'),
                    "query": query,
                    "total_items": data.get("totalItems", 0),
                    "book_title": volume_info.get("title"),
                    "book_authors": volume_info.get("authors", []),
                    "published_date": volume_info.get("publishedDate"),
                    "page_count": volume_info.get("pageCount"),
                    "categories": volume_info.get("categories", []),
                    "fetched_at": time.time(),
                    "api_url": api_url,
                    "image_size": google_size
                }
            )
            
        except requests.exceptions.Timeout:
            return CoverResult(
                image_bytes=None,
                source="google",
                url=api_url,
                metadata={
                    "error": "timeout",
                    "query": query,
                    "exception": "requests.exceptions.Timeout",
                    "isbn": isbn
                }
            )
            
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response else None
            return CoverResult(
                image_bytes=None,
                source="google",
                url=api_url,
                metadata={
                    "error": "http_error",
                    "status_code": status_code,
                    "query": query,
                    "exception": type(e).__name__,
                    "isbn": isbn
                }
            )
            
        except Exception as e:
            return CoverResult(
                image_bytes=None,
                source="google",
                url=api_url,
                metadata={
                    "error": "unexpected_error",
                    "query": query,
                    "exception": type(e).__name__,
                    "message": str(e),
                    "isbn": isbn
                }
            )    
        
    def _fetch_amazon_direct(self, isbn, title, author, size) -> CoverResult:
        """
        Direct fetch from Amazon - returns CoverResult object.
        WARNING: Use cautiously and respect Amazon's Terms of Service.
        """
        if not isbn:
            return CoverResult(
                image_bytes=None,
                source="amazon",
                url="",
                metadata={
                    "error": "no_isbn",
                    "reason": "ISBN required for Amazon direct fetch",
                    "title": title,
                    "author": author
                }
            )
        
        # Try multiple Amazon image URL patterns
        url_patterns = [
            f"https://images-na.ssl-images-amazon.com/images/P/{isbn}.01._SCLZZZZZZZ_.jpg",
            f"https://m.media-amazon.com/images/P/{isbn}.01._SCLZZZZZZZ_.jpg",
            f"https://images.amazon.com/images/P/{isbn}.01._SCLZZZZZZZ_.jpg",
        ]
        
        for url in url_patterns:
            try:
                response = self.session.get(url, timeout=8, headers={
                    "User-Agent": self.user_agent,
                    "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Referer": "https://www.amazon.com/"
                })
                
                # Check if valid image (not placeholder/error)
                if response.status_code == 200:
                    content_length = len(response.content)
                    content_type = response.headers.get('content-type', '')
                    
                    # Heuristic: valid book covers are usually > 10KB
                    # Placeholder/error images are often smaller
                    if content_length > 10000 and 'image' in content_type:
                        return CoverResult(
                            image_bytes=response.content,
                            source="amazon",
                            url=url,
                            metadata={
                                "size_bytes": content_length,
                                "content_type": content_type,
                                "isbn": isbn,
                                "url_pattern": url_patterns.index(url) + 1,
                                "status_code": response.status_code,
                                "fetched_at": time.time(),
                                "note": "Direct Amazon image fetch - check ToS compliance"
                            }
                        )
                    else:
                        # Image too small or wrong type - likely placeholder
                        continue
                        
            except requests.exceptions.Timeout:
                # Try next URL pattern
                continue
                
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 404:
                    # This URL pattern doesn't work, try next
                    continue
                else:
                    # Other HTTP error
                    return CoverResult(
                        image_bytes=None,
                        source="amazon",
                        url=url,
                        metadata={
                            "error": "http_error",
                            "status_code": e.response.status_code if e.response else None,
                            "isbn": isbn,
                            "url_pattern": url_patterns.index(url) + 1,
                            "exception": type(e).__name__
                        }
                    )
        
        # All URL patterns failed
        return CoverResult(
            image_bytes=None,
            source="amazon",
            url=url_patterns[-1] if url_patterns else "",
            metadata={
                "error": "no_valid_image",
                "reason": "All Amazon URL patterns failed or returned invalid images",
                "isbn": isbn,
                "title": title,
                "author": author,
                "patterns_tried": len(url_patterns),
                "note": "Amazon may have changed their image URL structure"
            }
        )

    def _optimize_image(self, image_bytes, max_size=(300, 400)):
        """
        Optimize image - imports PIL locally.
        This makes PIL optional for users who don't need optimization.
        """
        try:
            # LOCAL IMPORT - optional dependency
            from PIL import Image
            import io
            
            img = Image.open(io.BytesIO(image_bytes))
            # ... optimization logic ...
            
            return optimized_bytes
            
        except ImportError as e:
            # Clear error message
            logger.warning(f"PIL not available: {e}. Skipping optimization.")
            return image_bytes
            
        except Exception as e:
            # Don't crash on optimization errors
            logger.error(f"Optimization failed: {e}")
            return image_bytes

def get_cover_by_asin(fetcher, asin, size='M') -> CoverResult:
    """
    Try to fetch book cover using Kindle's ASIN.
    
    Returns:
        CoverResult object
    """
    if not asin:
        return CoverResult(
            image_bytes=None,
            source="asin",
            url="",
            metadata={
                "error": "no_asin",
                "reason": "ASIN is required",
                "asin": asin
            }
        )
    
    # First, try to convert ASIN to ISBN
    isbn = asin_to_isbn(asin)
    
    if isbn:
        # Use ISBN-based fetcher
        result = fetcher.get_cover(isbn=isbn, size=size)
        if result.success:
            result.metadata["original_asin"] = asin
            result.metadata["converted_isbn"] = isbn
            result.metadata["source"] = f"{result.source}_via_asin"
        return result
    
    # If no ISBN found, try direct ASIN methods
    return get_cover_by_asin_direct(fetcher, asin, size)

def asin_to_isbn(asin) -> Optional[str]:
    """Try to convert ASIN to ISBN."""
    # Check if ASIN is actually an ISBN-10
    if len(asin) == 10 and asin[:3].isdigit():
        try:
            # Try to convert to ISBN-13
            from isbnlib import to_isbn13
            return to_isbn13(asin)
        except:
            return asin  # Return as ISBN-10
    return None

def get_cover_by_asin_direct(fetcher, asin, size='M') -> CoverResult:
    """Try to get cover directly using ASIN."""
    # Try Amazon image URL patterns
    url_patterns = [
        f"https://images-na.ssl-images-amazon.com/images/P/{asin}.01._SCLZZZZZZZ_.jpg",
        f"https://m.media-amazon.com/images/P/{asin}.01._SCLZZZZZZZ_.jpg",
    ]
    
    for url in url_patterns:
        try:
            response = fetcher.session.get(url, timeout=8)
            if response.status_code == 200 and len(response.content) > 10000:
                return CoverResult(
                    image_bytes=response.content,
                    source="amazon_direct",
                    url=url,
                    metadata={
                        "asin": asin,
                        "method": "direct_amazon_url",
                        "url_pattern": url_patterns.index(url),
                        "size_bytes": len(response.content)
                    }
                )
        except:
            continue
    
    return CoverResult(
        image_bytes=None,
        source="amazon_direct",
        url=url_patterns[0] if url_patterns else "",
        metadata={
            "error": "all_patterns_failed",
            "asin": asin,
            "patterns_tried": len(url_patterns),
            "reason": "No valid image found from Amazon URLs"
        }
    )

def get_kindle_book_cover(book_info_record, size='M') -> CoverResult:
    """
    Unified function for Kindle2Anki to get book covers.
    
    Args:
        book_info_record: Dictionary with keys 'asin', 'title', 'authors'
        size: Image size ('S', 'M', 'L')
    
    Returns:
        CoverResult object with image data and metadata
    """
    fetcher = BookCoverFetcher()
    
    # First try ASIN-based methods
    if book_info_record.get('asin'):
        asin_result = get_cover_by_asin(fetcher, book_info_record['asin'], size=size)
        
        if asin_result.success:
            # Add Kindle-specific metadata
            asin_result.metadata.update({
                "kindle_source": "asin",
                "kindle_id": book_info_record.get('id'),
                "lang": book_info_record.get('lang', 'en')
            })
            return asin_result
    
    # Fallback to title/author search
    title_result = fetcher.get_cover(
        title=book_info_record.get('title'),
        author=book_info_record.get('authors'),
        size=size
    )
    
    if title_result.success:
        # Add Kindle-specific metadata
        title_result.metadata.update({
            "kindle_source": "title_author_search",
            "kindle_id": book_info_record.get('id'),
            "lang": book_info_record.get('lang', 'en'),
            "search_method": "title/author fallback"
        })
        return title_result
    
    # Ultimate fallback: placeholder with book info
    placeholder = fetcher.get_placeholder(
        title=book_info_record.get('title'),
        author=book_info_record.get('authors'),
        size=size
        )
    
    
    return CoverResult(
        image_bytes=placeholder,
        source="placeholder",
        url="",
        metadata={
            "kindle_source": "placeholder",
            "kindle_id": book_info_record.get('id'),
            "title": book_info_record.get('title'),
            "authors": book_info_record.get('authors'),
            "lang": book_info_record.get('lang', 'en'),
            "reason": "All sources failed - using placeholder",
            "is_placeholder": True
        }
    )

def test_kindle_covers():
    """Test cover fetching with multiple Kindle books."""
    test_books = [
        {
            'id': 'Harry_Potter:CB123456',
            'asin': '9780545010221',  # This is actually an ISBN
            'title': 'Harry Potter and the Deathly Hallows',
            'authors': 'J.K. Rowling',
            'lang': 'en'
        },
        {
            'id': 'Grapes_of_Wrath:CB079181',
            'asin': '90f28551-12da-4d52-9691-8391d8562245',  # UUID-like ASIN
            'title': 'The Grapes of Wrath',
            'authors': 'John Steinbeck',
            'lang': 'en'
        },
        {
            'id': 'Unknown_Book:CB999999',
            'asin': None,  # No ASIN
            'title': 'Totally Fake Book That Does Not Exist',
            'authors': 'Imaginary Author',
            'lang': 'en'
        }
    ]
    
    fetcher = BookCoverFetcher(cache_dir="./test_covers")
    
    print("📚 Kindle Cover Fetch Test")
    print("=" * 50)
    
    results = []
    for book in test_books:
        print(f"\n📖 {book['title']}")
        print(f"   Author: {book['authors']}")
        
        result = get_kindle_book_cover(book, size='M')
        results.append((book, result))
        
        # Status indicator
        if result.success and not result.metadata.get('is_placeholder'):
            print(f"   ✅ Cover found via: {result.source}")
        elif result.metadata.get('is_placeholder'):
            print(f"   ⚠️  No cover found, using placeholder")
        else:
            print(f"   ❌ Failed: {result.metadata.get('error', 'Unknown error')}")
        
        # Save cover
        if result.image_bytes:
            safe_title = book['title'].replace(' ', '_').replace(':', '')
            filename = f"{safe_title}.jpg"
            with open(f"./test_covers/{filename}", "wb") as f:
                f.write(result.image_bytes)
            print(f"   💾 Saved: {filename}")
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 Test Summary:")
    
    total = len(results)
    successful = sum(1 for _, r in results if r.success and not r.metadata.get('is_placeholder'))
    placeholders = sum(1 for _, r in results if r.metadata.get('is_placeholder'))
    failed = total - successful - placeholders
    
    print(f"   Total books: {total}")
    print(f"   Successful covers: {successful}")
    print(f"   Placeholders used: {placeholders}")
    print(f"   Failed: {failed}")
    
    # Show sources used
    sources = {}
    for _, result in results:
        source = result.source
        sources[source] = sources.get(source, 0) + 1
    
    print(f"\n   Sources used:")
    for source, count in sources.items():
        print(f"     {source}: {count}")
    
    return results

def diagnose_return_types():
    """Find which function returns wrong type."""
    from get_bookcover import BookCoverFetcher, get_cover_by_asin
    
    fetcher = BookCoverFetcher()
    
    print("1. Testing fetcher.get_cover()...")
    result1 = fetcher.get_cover(title="Test Book", author="Test Author")
    print(f"   Type: {type(result1)}")
    
    print("\n2. Testing get_cover_by_asin()...")
    result2 = get_cover_by_asin(fetcher, "fake_asin", size='M')
    print(f"   Type: {type(result2)}")
    
    print("\n3. Testing get_kindle_book_cover()...")
    test_book = {
        'title': 'Test Book',
        'authors': 'Test Author',
        'asin': None,
        'id': 'test:123',
        'lang': 'en'
    }
    result3 = get_kindle_book_cover(test_book, size='M')
    print(f"   Type: {type(result3)}")
    
    # Summary
    print("\n" + "="*50)
    print("SUMMARY:")
    for name, result in [("fetcher.get_cover", result1), 
                         ("get_cover_by_asin", result2),
                         ("get_kindle_book_cover", result3)]:
        if isinstance(result, CoverResult):
            print(f"✅ {name}: Returns CoverResult")
        else:
            print(f"❌ {name}: Returns {type(result).__name__}")




def main():
    """Concise version of main function."""
    fetcher = BookCoverFetcher(cache_dir="./book_covers")
    
    kindle_entry = {
        'id': 'The_Grapes_of_Wrath:CB079181',
        'asin': '90f28551-12da-4d52-9691-8391d8562245', 
        'title': 'The Grapes of Wrath',
        'authors': 'John Steinbeck'
    }
    
    result = get_kindle_book_cover(kindle_entry, size='M')
    
    # Save the cover regardless (cover or placeholder)
    filename = f"{kindle_entry['title'].replace(' ', '_')}_cover.jpg"
    with open(filename, "wb") as f:
        f.write(result.image_bytes)
    
    # Report results
    status = "✅" if result.success and not result.metadata.get('is_placeholder') else "⚠️"
    print(f"{status} {kindle_entry['title']}")
    print(f"   Source: {result.source}")
    print(f"   Saved: {filename} ({len(result.image_bytes):,} bytes)")
    
    if result.metadata.get('is_placeholder'):
        print("   Note: Using placeholder (no real cover found)")
    
    return result


# run this directly for a single test
if __name__ == "__main__":
    # Run single book test
    # main()
    # Run it
    # diagnose_return_types()
    # Or run comprehensive test
    test_kindle_covers()


