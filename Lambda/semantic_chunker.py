import re
import logging
from typing import List, Dict, Tuple
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.docstore.document import Document

logger = logging.getLogger(__name__)

class SemanticChunker:
    """
    Intelligent chunker that preserves semantic structure including tables,
    lists, and related content blocks.
    """
    
    def __init__(self, max_chunk_size: int = 1500, min_chunk_size: int = 200):
        self.max_chunk_size = max_chunk_size
        self.min_chunk_size = min_chunk_size
        
        # Patterns for structured content
        self.table_patterns = [
            r'(?:\|[^\n]*\|[\s]*\n){2,}',  # Markdown tables
            r'(?:[^\n]*\t[^\n]*\n){2,}',   # Tab-separated tables
            r'(?:[A-Za-z0-9\s]+:\s*[^\n]+\n){3,}',  # Key-value pairs
            r'(?:\d+[\.\)]\s+[^\n]+\n){2,}',  # Numbered lists
            r'(?:[-\*\+]\s+[^\n]+\n){2,}',    # Bullet lists
        ]
        
        # Semantic boundaries
        self.section_headers = [
            r'^#{1,6}\s+.+$',  # Markdown headers
            r'^[A-Z][A-Z\s]{2,}:?\s*$',  # ALL CAPS headers
            r'^\d+\.\s+[A-Z][^.]*$',  # Numbered sections
            r'^[A-Z][^.]*:$',  # Title with colon
        ]
        
        # Content type indicators
        self.spec_indicators = [
            r'specifications?', r'features?', r'options?', r'equipment',
            r'dimensions?', r'capacity', r'performance', r'engine',
            r'transmission', r'fuel', r'mpg', r'horsepower', r'torque'
        ]
        
    def identify_content_blocks(self, text: str) -> List[Dict]:
        """Identify and classify content blocks in the text."""
        blocks = []
        lines = text.split('\n')
        current_block = {'type': 'text', 'content': '', 'start_line': 0}
        
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            
            # Check for table patterns
            if self._is_table_line(line, lines, i):
                if current_block['type'] != 'table':
                    if current_block['content'].strip():
                        blocks.append(current_block)
                    current_block = {'type': 'table', 'content': line + '\n', 'start_line': i}
                else:
                    current_block['content'] += line + '\n'
            
            # Check for section headers
            elif self._is_section_header(line_stripped):
                if current_block['content'].strip():
                    blocks.append(current_block)
                current_block = {'type': 'header', 'content': line + '\n', 'start_line': i}
            
            # Check for lists
            elif self._is_list_item(line_stripped):
                if current_block['type'] not in ['list', 'header']:
                    if current_block['content'].strip():
                        blocks.append(current_block)
                    current_block = {'type': 'list', 'content': line + '\n', 'start_line': i}
                else:
                    current_block['content'] += line + '\n'
            
            # Regular text
            else:
                if current_block['type'] not in ['text', 'header']:
                    if current_block['content'].strip():
                        blocks.append(current_block)
                    current_block = {'type': 'text', 'content': line + '\n', 'start_line': i}
                else:
                    current_block['content'] += line + '\n'
        
        # Add final block
        if current_block['content'].strip():
            blocks.append(current_block)
        
        return blocks
    
    def _is_table_line(self, line: str, all_lines: List[str], line_idx: int) -> bool:
        """Check if line is part of a table structure."""
        line_stripped = line.strip()
        
        # Markdown table indicators
        if '|' in line and line.count('|') >= 2:
            return True
        
        # Tab-separated values
        if '\t' in line and len(line.split('\t')) >= 3:
            return True
        
        # Key-value pairs (common in specs)
        if re.match(r'^[A-Za-z0-9\s]+:\s*[^\n]+$', line_stripped):
            # Check if next/previous lines are similar
            context_lines = []
            for offset in [-1, 1]:
                if 0 <= line_idx + offset < len(all_lines):
                    context_lines.append(all_lines[line_idx + offset].strip())
            
            similar_pattern = any(
                re.match(r'^[A-Za-z0-9\s]+:\s*[^\n]+$', ctx_line)
                for ctx_line in context_lines
            )
            return similar_pattern
        
        return False
    
    def _is_section_header(self, line: str) -> bool:
        """Check if line is a section header."""
        for pattern in self.section_headers:
            if re.match(pattern, line, re.MULTILINE):
                return True
        return False
    
    def _is_list_item(self, line: str) -> bool:
        """Check if line is a list item."""
        return bool(re.match(r'^(\d+[\.\)]\s+|[-\*\+]\s+)', line))
    
    def _merge_related_blocks(self, blocks: List[Dict]) -> List[Dict]:
        """Merge semantically related blocks."""
        if not blocks:
            return blocks
        
        merged = []
        current_group = [blocks[0]]
        
        for i in range(1, len(blocks)):
            current_block = blocks[i]
            prev_block = current_group[-1]
            
            # Merge conditions
            should_merge = False
            
            # Merge header with following content
            if prev_block['type'] == 'header' and current_block['type'] in ['text', 'list']:
                should_merge = True
            
            # Merge consecutive lists
            elif prev_block['type'] == 'list' and current_block['type'] == 'list':
                should_merge = True
            
            # Merge short text blocks
            elif (prev_block['type'] == 'text' and current_block['type'] == 'text' and
                  len(prev_block['content']) < 300):
                should_merge = True
            
            # Keep tables separate (this is key for your use case)
            elif current_block['type'] == 'table':
                should_merge = False
            
            if should_merge and self._get_group_size(current_group + [current_block]) < self.max_chunk_size:
                current_group.append(current_block)
            else:
                merged.append(self._combine_group(current_group))
                current_group = [current_block]
        
        # Add final group
        if current_group:
            merged.append(self._combine_group(current_group))
        
        return merged
    
    def _get_group_size(self, group: List[Dict]) -> int:
        """Calculate total character count of a group."""
        return sum(len(block['content']) for block in group)
    
    def _combine_group(self, group: List[Dict]) -> Dict:
        """Combine a group of blocks into a single block."""
        if len(group) == 1:
            return group[0]
        
        combined_content = ''.join(block['content'] for block in group)
        primary_type = group[0]['type']
        
        # Determine the most important type in the group
        if any(block['type'] == 'table' for block in group):
            primary_type = 'table'
        elif any(block['type'] == 'header' for block in group):
            primary_type = 'header'
        
        return {
            'type': primary_type,
            'content': combined_content,
            'start_line': group[0]['start_line'],
            'block_count': len(group)
        }
    
    def _split_oversized_blocks(self, blocks: List[Dict]) -> List[Dict]:
        """Split blocks that exceed max_chunk_size while preserving structure."""
        result = []
        
        for block in blocks:
            if len(block['content']) <= self.max_chunk_size:
                result.append(block)
                continue
            
            # For tables, try to split by logical rows
            if block['type'] == 'table':
                result.extend(self._split_table_block(block))
            else:
                # For other content, use sentence-aware splitting
                result.extend(self._split_text_block(block))
        
        return result
    
    def _split_table_block(self, block: Dict) -> List[Dict]:
        """Split table while keeping related rows together."""
        lines = block['content'].split('\n')
        chunks = []
        current_chunk = []
        current_size = 0
        
        # Try to identify table header
        header_lines = []
        data_start = 0
        
        for i, line in enumerate(lines[:3]):  # Check first 3 lines for headers
            if line.strip() and ('|' in line or ':' in line or line.isupper()):
                header_lines.append(line)
                data_start = i + 1
            else:
                break
        
        # Add header to each chunk
        header_text = '\n'.join(header_lines) + '\n' if header_lines else ''
        header_size = len(header_text)
        
        for line in lines[data_start:]:
            line_with_newline = line + '\n'
            
            if current_size + len(line_with_newline) + header_size > self.max_chunk_size and current_chunk:
                # Create chunk with header
                chunk_content = header_text + ''.join(current_chunk)
                chunks.append({
                    'type': 'table',
                    'content': chunk_content,
                    'start_line': block['start_line'],
                    'is_continuation': len(chunks) > 0
                })
                current_chunk = []
                current_size = header_size
            
            current_chunk.append(line_with_newline)
            current_size += len(line_with_newline)
        
        # Add final chunk
        if current_chunk:
            chunk_content = header_text + ''.join(current_chunk)
            chunks.append({
                'type': 'table',
                'content': chunk_content,
                'start_line': block['start_line'],
                'is_continuation': len(chunks) > 0
            })
        
        return chunks if chunks else [block]
    
    def _split_text_block(self, block: Dict) -> List[Dict]:
        """Split text block using sentence boundaries."""
        # Use RecursiveCharacterTextSplitter as fallback for oversized text
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.max_chunk_size,
            chunk_overlap=100,
            separators=['\n\n', '\n', '. ', '! ', '? ', '; ', ', ', ' ']
        )
        
        text_chunks = splitter.split_text(block['content'])
        
        result = []
        for i, chunk_text in enumerate(text_chunks):
            result.append({
                'type': block['type'],
                'content': chunk_text,
                'start_line': block['start_line'],
                'is_continuation': i > 0
            })
        
        return result
    
    def chunk_text(self, text: str, doc_name: str = "") -> List[Document]:
        """
        Main method to chunk text semantically.
        
        Args:
            text: Input text to chunk
            doc_name: Document name for metadata
            
        Returns:
            List of Document objects with semantic chunks
        """
        logger.info(f"Starting semantic chunking | Text length: {len(text)} | Doc: {doc_name}")
        
        # Step 1: Identify content blocks
        blocks = self.identify_content_blocks(text)
        logger.info(f"Identified {len(blocks)} content blocks")
        
        # Step 2: Merge related blocks
        merged_blocks = self._merge_related_blocks(blocks)
        logger.info(f"Merged to {len(merged_blocks)} semantic groups")
        
        # Step 3: Split oversized blocks
        final_blocks = self._split_oversized_blocks(merged_blocks)
        logger.info(f"Final chunks: {len(final_blocks)}")
        
        # Step 4: Create Document objects
        documents = []
        for i, block in enumerate(final_blocks):
            # Enhanced content with document context and better formatting
            block_content = block['content'].strip()
            if doc_name:
                content = f"Document: {doc_name}\n\n{block_content}"
            else:
                content = block_content
            
            # Add context clues for better search
            if block['type'] == 'table':
                content = f"SPECIFICATIONS TABLE:\n{content}"
            elif any(keyword in content.lower() for keyword in ['dimension', 'length', 'width', 'height', 'capacity', 'fuel', 'engine']):
                content = f"TECHNICAL SPECIFICATIONS:\n{content}"
            
            # Add English translations for Hebrew specifications
            hebrew_translations = {
                'אורך כללי': 'Overall Length',
                'רוחב כללי': 'Overall Width', 
                'גובה כללי': 'Overall Height',
                'מרווח סרנים': 'Wheelbase',
                'מרווח גחון': 'Ground Clearance',
                'צריכת דלק': 'Fuel Consumption',
                'נפח דלק': 'Fuel Tank Capacity',
                'משקל עצמי': 'Curb Weight',
                'מנוע': 'Engine',
                'הספק מירבי': 'Maximum Power',
                'מומנט מירבי': 'Maximum Torque',
                'מהירות מירבית': 'Maximum Speed'
            }
            
            for hebrew, english in hebrew_translations.items():
                if hebrew in content:
                    content += f"\n{english}: [Hebrew: {hebrew}]"
            
            # Rich metadata
            metadata = {
                "source": doc_name,
                "chunk_id": i,
                "total_chunks": len(final_blocks),
                "content_type": block['type'],
                "start_line": block.get('start_line', 0),
                "is_continuation": block.get('is_continuation', False),
                "block_count": block.get('block_count', 1),
                "chunk_size": len(content)
            }
            
            # Add content-specific metadata
            if block['type'] == 'table':
                metadata['contains_structured_data'] = True
                metadata['table_rows'] = content.count('\n')
            elif block['type'] == 'list':
                metadata['contains_list'] = True
                metadata['list_items'] = len(re.findall(r'^(\d+[\.\)]\s+|[-\*\+]\s+)', content, re.MULTILINE))
            
            # Detect specification content with enhanced patterns including Hebrew
            spec_patterns = self.spec_indicators + [
                r'\d+\s*(mm|cm|m|liter|l|hp|kw|kg|ton)',  # Measurements
                r'fuel\s*tank',
                r'ground\s*clearance', 
                r'wheelbase',
                r'\d+\.\d+\s*l',  # Engine displacement
                r'\d+\s*hp',  # Horsepower
                r'אורך|רוחב|גובה|מרווח|צריכת|נפח|משקל|מנוע|הספק|מומנט',  # Hebrew specs
            ]
            if any(re.search(pattern, content.lower()) for pattern in spec_patterns):
                metadata['contains_specifications'] = True
                metadata['specification_type'] = 'technical_data'
            
            doc = Document(page_content=content, metadata=metadata)
            documents.append(doc)
        
        logger.info(f"Semantic chunking complete | Documents: {len(documents)} | Types: {[d.metadata['content_type'] for d in documents]}")
        return documents

def create_semantic_chunks(text: str, doc_name: str = "", max_chunk_size: int = 1500) -> List[Document]:
    """
    Convenience function to create semantic chunks.
    
    Args:
        text: Input text
        doc_name: Document name
        max_chunk_size: Maximum chunk size in characters
        
    Returns:
        List of semantically chunked Document objects
    """
    chunker = SemanticChunker(max_chunk_size=max_chunk_size)
    return chunker.chunk_text(text, doc_name)