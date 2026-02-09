"""Match fields between source and target documents."""
from difflib import SequenceMatcher

def match_fields(source_data, target_fields):
    """
    Match source fields to target fields using fuzzy matching.
    
    Args:
        source_data: dict of {field_name: value}
        target_fields: list of field names from target document
    
    Returns:
        dict with certain_matches and uncertain_matches
    """
    certain_matches = []
    uncertain_matches = []
    
    for target_field in target_fields:
        best_match = None
        best_score = 0
        
        for source_field in source_data.keys():
            score = similarity(target_field, source_field)
            if score > best_score:
                best_score = score
                best_match = source_field
        
        if best_match:
            match = {
                'target_field': target_field,
                'source_field': best_match,
                'confidence': best_score
            }
            
            if best_score >= 0.8:
                certain_matches.append(match)
            elif best_score >= 0.5:
                uncertain_matches.append(match)
    
    return {
        'certain_matches': certain_matches,
        'uncertain_matches': uncertain_matches
    }

def similarity(a, b):
    """Calculate similarity between two strings (0-1)."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()
