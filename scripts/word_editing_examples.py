#!/usr/bin/env python3
"""
Example script demonstrating practical use cases for Word document editing.
This shows how to use the Word editing functionality in real-world scenarios.
"""
import os
import sys
from pathlib import Path
from datetime import datetime

# Add Lambda directory to path for imports
lambda_dir = Path(__file__).parent.parent / 'Lambda'
sys.path.insert(0, str(lambda_dir))

from office_converter import create_docx, edit_docx, extract_docx

def example_1_create_invoice():
    """Example: Create a professional invoice document."""
    print("\n=== Example 1: Creating an Invoice ===")
    
    invoice_number = "INV-2025-001"
    customer_name = "Acme Corporation"
    invoice_date = datetime.now().strftime("%B %d, %Y")
    
    content = {
        'title': f'INVOICE {invoice_number}',
        'paragraphs': [
            f'Date: {invoice_date}',
            f'Bill To: {customer_name}',
            '123 Business Street',
            'City, State 12345',
            '',
            'Thank you for your business!'
        ],
        'headings': [
            {'text': 'Items', 'level': 1}
        ],
        'tables': [
            {
                'rows': 5,
                'cols': 4,
                'data': [
                    ['Item', 'Description', 'Quantity', 'Amount'],
                    ['Service A', 'Consulting Services', '10 hrs', '$1,500.00'],
                    ['Service B', 'Development Work', '20 hrs', '$3,000.00'],
                    ['Service C', 'Testing & QA', '5 hrs', '$750.00'],
                    ['', '', 'TOTAL:', '$5,250.00']
                ]
            }
        ]
    }
    
    output_path = f'/tmp/invoice_{invoice_number}.docx'
    if create_docx(output_path, content):
        print(f"✓ Invoice created: {output_path}")
        return output_path
    else:
        print("✗ Failed to create invoice")
        return None

def example_2_update_report():
    """Example: Update an existing report with new findings."""
    print("\n=== Example 2: Updating a Report ===")
    
    # Create a base report
    base_path = '/tmp/base_report.docx'
    create_docx(base_path, {
        'title': 'Quarterly Report - Q4 2024',
        'headings': [
            {'text': 'Executive Summary', 'level': 1}
        ],
        'paragraphs': [
            'This report covers the fourth quarter of 2024.',
            'Key metrics show positive growth across all sectors.'
        ]
    })
    
    # Update with new section
    output_path = '/tmp/updated_report.docx'
    modifications = {
        'add_heading': [
            {'text': 'New Developments', 'level': 1},
            {'text': 'Q1 2025 Outlook', 'level': 2}
        ],
        'add_paragraph': [
            {'text': 'Recent market analysis indicates continued growth potential.'},
            {'text': 'We anticipate a 15% increase in revenue for Q1 2025.'}
        ],
        'add_table': {
            'rows': 4,
            'cols': 3,
            'data': [
                ['Quarter', 'Revenue', 'Growth'],
                ['Q3 2024', '$1.2M', '+8%'],
                ['Q4 2024', '$1.5M', '+12%'],
                ['Q1 2025 (Projected)', '$1.7M', '+15%']
            ]
        }
    }
    
    if edit_docx(base_path, output_path, modifications):
        print(f"✓ Report updated: {output_path}")
        text, _ = extract_docx(output_path)
        print(f"  Document contains {len(text)} characters")
        return output_path
    else:
        print("✗ Failed to update report")
        return None

def example_3_personalize_template():
    """Example: Personalize a template letter for multiple recipients."""
    print("\n=== Example 3: Personalizing Template Letters ===")
    
    # Create template
    template_path = '/tmp/template_letter.docx'
    create_docx(template_path, {
        'paragraphs': [
            'Dear {NAME},',
            '',
            'We are pleased to inform you that your application for {POSITION} has been approved.',
            'Your start date will be {START_DATE}.',
            '',
            'Welcome to the team!',
            '',
            'Best regards,',
            'HR Department'
        ]
    })
    
    # Personalize for multiple recipients
    recipients = [
        {'name': 'Alice Johnson', 'position': 'Software Engineer', 'date': 'January 15, 2025'},
        {'name': 'Bob Smith', 'position': 'Data Analyst', 'date': 'January 22, 2025'},
        {'name': 'Carol Williams', 'position': 'Product Manager', 'date': 'February 1, 2025'}
    ]
    
    personalized_docs = []
    for recipient in recipients:
        output_path = f'/tmp/letter_{recipient["name"].replace(" ", "_")}.docx'
        
        modifications = {
            'replace_text': [
                {'old': '{NAME}', 'new': recipient['name']},
                {'old': '{POSITION}', 'new': recipient['position']},
                {'old': '{START_DATE}', 'new': recipient['date']}
            ]
        }
        
        if edit_docx(template_path, output_path, modifications):
            personalized_docs.append(output_path)
            print(f"  ✓ Created letter for {recipient['name']}")
    
    print(f"✓ Created {len(personalized_docs)} personalized letters")
    return personalized_docs

def example_4_meeting_notes():
    """Example: Generate structured meeting notes."""
    print("\n=== Example 4: Creating Meeting Notes ===")
    
    meeting_date = datetime.now().strftime("%Y-%m-%d")
    
    content = {
        'title': 'Team Meeting Notes',
        'paragraphs': [
            f'Date: {meeting_date}',
            'Attendees: Alice, Bob, Carol, David',
            'Duration: 1 hour'
        ],
        'headings': [
            {'text': 'Agenda Items', 'level': 1},
            {'text': '1. Project Status Update', 'level': 2}
        ],
        'paragraphs': [
            'The project is on track for Q1 delivery.',
            'All milestones have been met.',
        ],
        'headings': [
            {'text': '2. Action Items', 'level': 2}
        ],
        'tables': [
            {
                'rows': 4,
                'cols': 3,
                'data': [
                    ['Task', 'Owner', 'Due Date'],
                    ['Update documentation', 'Alice', '2025-12-20'],
                    ['Code review', 'Bob', '2025-12-18'],
                    ['Testing plan', 'Carol', '2025-12-22']
                ]
            }
        ],
        'headings': [
            {'text': '3. Next Meeting', 'level': 2}
        ],
        'paragraphs': [
            'Scheduled for next week, same time.',
            'Focus will be on deployment planning.'
        ]
    }
    
    output_path = f'/tmp/meeting_notes_{meeting_date}.docx'
    if create_docx(output_path, content):
        print(f"✓ Meeting notes created: {output_path}")
        return output_path
    else:
        print("✗ Failed to create meeting notes")
        return None

def example_5_batch_updates():
    """Example: Batch update multiple documents."""
    print("\n=== Example 5: Batch Document Updates ===")
    
    # Create several documents
    docs = []
    for i in range(1, 4):
        doc_path = f'/tmp/document_{i}.docx'
        create_docx(doc_path, {
            'title': f'Document {i}',
            'paragraphs': [
                'This is a DRAFT version.',
                'Created on 2024-12-15.',
                'Status: PENDING'
            ]
        })
        docs.append(doc_path)
    
    # Batch update all documents
    modifications = {
        'replace_text': [
            {'old': 'DRAFT', 'new': 'FINAL'},
            {'old': '2024-12-15', 'new': '2025-12-15'},
            {'old': 'PENDING', 'new': 'APPROVED'}
        ],
        'add_paragraph': {
            'text': 'Document has been approved and finalized.'
        }
    }
    
    updated = 0
    for doc_path in docs:
        if edit_docx(doc_path, modifications=modifications):
            updated += 1
            print(f"  ✓ Updated {os.path.basename(doc_path)}")
    
    print(f"✓ Successfully updated {updated} documents")
    return updated

def main():
    """Run all examples."""
    print("=" * 70)
    print("Word Document Editing - Practical Examples")
    print("=" * 70)
    
    try:
        # Run all examples
        example_1_create_invoice()
        example_2_update_report()
        example_3_personalize_template()
        example_4_meeting_notes()
        example_5_batch_updates()
        
        print("\n" + "=" * 70)
        print("All examples completed successfully!")
        print("Check /tmp/ directory for generated documents")
        print("=" * 70)
        
    except Exception as e:
        print(f"\n✗ Error running examples: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
