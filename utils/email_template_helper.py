import os
import logging
from pathlib import Path

# Configure logger
logger = logging.getLogger('email_template_helper')

class EmailTemplateHelper:
    """Helper class for loading and rendering email templates"""
    
    @staticmethod
    def get_template_path():
        """Get the path to email templates directory"""
        return Path(__file__).parent.parent / 'templates' / 'email'
    
    @staticmethod
    def load_template(template_name):
        """
        Load an email template from file
        
        Args:
            template_name: Name of the template file (e.g., 'base_template.html')
            
        Returns:
            str: Template content or None if file not found
        """
        try:
            template_path = EmailTemplateHelper.get_template_path() / template_name
            
            if not template_path.exists():
                logger.error(f"Template file not found: {template_path}")
                return None
                
            with open(template_path, 'r', encoding='utf-8') as file:
                return file.read()
                
        except Exception as e:
            logger.error(f"Error loading template {template_name}: {str(e)}")
            return None
    
    @staticmethod
    def render_template(template_content, **variables):
        """
        Render template with variables using simple string replacement
        
        Args:
            template_content: Template content string
            **variables: Variables to replace in template
            
        Returns:
            str: Rendered template
        """
        if not template_content:
            return ""
            
        try:
            # Use simple string replacement for template variables
            # Format: {{variable_name}}
            rendered = template_content
            
            for key, value in variables.items():
                placeholder = f"{{{{{key}}}}}"
                rendered = rendered.replace(placeholder, str(value))
            
            return rendered
            
        except Exception as e:
            logger.error(f"Error rendering template: {str(e)}")
            return template_content
    
    @staticmethod
    def create_button_html(url, text, button_class="btn-primary", icon=""):
        """
        Create a button HTML snippet
        
        Args:
            url: Button URL
            text: Button text
            button_class: CSS class for button styling
            icon: Optional icon/emoji to include
            
        Returns:
            str: Button HTML
        """
        button_text = f"{icon} {text}".strip()
        
        return f"""
        <table role="presentation" cellspacing="0" cellpadding="0" border="0" style="margin: 30px auto;">
            <tr>
                <td style="padding: 0 8px;" class="mobile-btn">
                    <a href="{url}" class="{button_class}" style="display: inline-block; padding: 16px 32px; background: linear-gradient(135deg, #DA8FFF 0%, #B8A2DC 100%); color: #FFFFFF; text-decoration: none; border-radius: 9999px; font-weight: 700; font-size: 16px; box-shadow: 0 8px 16px rgba(218, 143, 255, 0.3); font-family: 'Quicksand', sans-serif, Arial, sans-serif;">
                        {button_text}
                    </a>
                </td>
            </tr>
        </table>
        """
    
    @staticmethod
    def create_gradient_text(text, gradient_class="text-gradient"):
        """
        Create gradient text HTML
        
        Args:
            text: Text to apply gradient to
            gradient_class: CSS class for gradient
            
        Returns:
            str: Gradient text HTML
        """
        return f'<span style="background: linear-gradient(135deg, #DA8FFF 0%, #FBBEBF 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; font-weight: 600;">{text}</span>'
    
    @staticmethod
    def get_base_email_template(**variables):
        """
        Get the base email template with variables filled in
        
        Args:
            **variables: Template variables
            
        Returns:
            str: Rendered email template
        """
        # Set default values for required variables
        defaults = {
            'preheader_text': 'Witaj w DawnoTemu! Twój głos opowiada baśnie, zawsze gdy potrzebujesz ✨',
            'email_title': 'Witaj w DawnoTemu! 👋',
            'email_content': '',
            'button_section': ''
        }
        
        # Merge defaults with provided variables
        template_vars = {**defaults, **variables}
        
        # Load and render the base template
        template_content = EmailTemplateHelper.load_template('base_template.html')
        
        if not template_content:
            logger.error("Failed to load base email template")
            return ""
        
        return EmailTemplateHelper.render_template(template_content, **template_vars) 