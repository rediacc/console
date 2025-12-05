import 'styled-components';
import { StyledTheme } from './styledTheme';

declare module 'styled-components' {
  export interface DefaultTheme extends StyledTheme {}
}
