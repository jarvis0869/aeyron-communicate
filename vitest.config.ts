import {defineConfig} from 'vitest/config';
import vite from './vite.config';
export default defineConfig({plugins:vite.plugins, test:{exclude:['tests/e2e/**','node_modules/**','dist/**']}});
