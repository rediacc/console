/**
 * ESLint rule to prevent multiple TypedTFunction props in interfaces
 *
 * This rule detects when interfaces or type definitions have multiple
 * translation function props (like t, tCommon, tSystem) and suggests
 * consolidating them into a single "t" prop with namespace prefixes.
 *
 * Example of violation:
 *   interface Props {
 *     t: TypedTFunction;
 *     tCommon: TypedTFunction;  // ERROR: Use t('common:...') instead
 *   }
 *
 * Correct pattern:
 *   interface Props {
 *     t: TypedTFunction;
 *   }
 *   // Use: t('common:actions.cancel'), t('system:tables.name')
 */

/** @type {import('eslint').Rule.RuleModule} */
export const noDuplicateTranslationProps = {
  meta: {
    type: 'problem',
    docs: {
      description: 'Disallow multiple TypedTFunction props in interfaces/types',
      recommended: true,
    },
    messages: {
      duplicateTranslationProps:
        'Multiple TypedTFunction props detected ({{props}}). Use a single "t" prop with namespace prefixes instead (e.g., t(\'common:...\'), t(\'system:...\')).',
    },
    schema: [],
  },

  create(context) {
    /**
     * Get the type name from a type annotation node
     */
    function getTypeName(typeAnnotation) {
      if (!typeAnnotation) return null;

      // Handle TSTypeReference (e.g., TypedTFunction)
      if (typeAnnotation.type === 'TSTypeReference') {
        if (typeAnnotation.typeName?.type === 'Identifier') {
          return typeAnnotation.typeName.name;
        }
      }

      return null;
    }

    /**
     * Check if a property has TypedTFunction type
     */
    function isTypedTFunctionProp(prop) {
      // Handle TSPropertySignature (interface property)
      if (prop.type === 'TSPropertySignature') {
        const typeName = getTypeName(prop.typeAnnotation?.typeAnnotation);
        return typeName === 'TypedTFunction';
      }

      // Handle Property in type literal
      if (prop.type === 'Property') {
        const typeName = getTypeName(prop.value?.typeAnnotation?.typeAnnotation);
        return typeName === 'TypedTFunction';
      }

      return false;
    }

    /**
     * Get the property name
     */
    function getPropName(prop) {
      if (prop.key?.type === 'Identifier') {
        return prop.key.name;
      }
      return null;
    }

    /**
     * Check a list of properties for multiple TypedTFunction types
     */
    function checkProperties(properties, node) {
      const translationProps = properties
        .filter(isTypedTFunctionProp)
        .map(getPropName)
        .filter(Boolean);

      if (translationProps.length > 1) {
        context.report({
          node,
          messageId: 'duplicateTranslationProps',
          data: {
            props: translationProps.join(', '),
          },
        });
      }
    }

    return {
      // Check interface declarations
      TSInterfaceDeclaration(node) {
        if (node.body?.body) {
          checkProperties(node.body.body, node);
        }
      },

      // Check type alias declarations with type literals
      TSTypeAliasDeclaration(node) {
        if (node.typeAnnotation?.type === 'TSTypeLiteral') {
          checkProperties(node.typeAnnotation.members, node);
        }
      },

      // Check inline type literals (e.g., in function parameters)
      TSTypeLiteral(node) {
        // Skip if this is already handled by TSTypeAliasDeclaration
        if (node.parent?.type === 'TSTypeAliasDeclaration') {
          return;
        }
        checkProperties(node.members, node);
      },
    };
  },
};

export default noDuplicateTranslationProps;
