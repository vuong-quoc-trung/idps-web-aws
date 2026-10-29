# DUT - THÔNG TIN SINH VIÊN

Frontend React/TypeScript của Student Web. Từ gốc repository, chạy
`bash student-web/frontend/run.sh`; script dùng Node local tại `.local-node/24`
nếu có và cài dependencies khi thiếu `node_modules`. Backend cần chạy ở cổng 8080.
Khi cập nhật dependencies, chạy `npm ci` trong thư mục này với Node phù hợp Vite 8.

Kiểm tra bản production bằng `npm run build`. Nếu Web VM phục vụ thư mục `dist`
qua Nginx, cần build lại trên Web VM sau khi pull; nếu dùng Vite dev, khởi động lại
frontend và tải lại trình duyệt. Bản build không được lưu vào Git.

## Giữ các cập nhật khi tích hợp nhánh

Logo DUT, title/favicon, footer liên hệ, header tài khoản, trang học vụ sinh viên
và phản hồi khi sửa hồ sơ được khôi phục từ `feat/student-database` (mốc `c823127`).
Commit `e1447b2` từng ghi đè các phần này khi lấy frontend từ `feat/student-ui`.
Nhánh nguồn đã nằm trong lịch sử hiện tại nên merge lại đơn thuần không phục hồi
những file đã bị xóa/ghi đè bởi commit sau đó.

Khi nhận thay đổi từ nhánh UI, so sánh và tích hợp theo phần thay vì thay nguyên
thư mục frontend. Giữ `AppFooter`, asset `public/images/dut-logo.jpg`, layout trong
`App.tsx`, phân quyền trang học vụ và các sửa lỗi xác thực/URL hiện hành. Đối chiếu
API Student mới và audit trước khi thay backend bằng phiên bản của nhánh cũ.

## Tài liệu template Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the ESLint configuration

If you are developing a production application, we recommend updating the configuration to enable type-aware lint rules:

```js
export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...

      // Remove tseslint.configs.recommended and replace with this
      tseslint.configs.recommendedTypeChecked,
      // Alternatively, use this for stricter rules
      tseslint.configs.strictTypeChecked,
      // Optionally, add this for stylistic rules
      tseslint.configs.stylisticTypeChecked,

      // Other configs...
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])

```

You can also install [eslint-plugin-react-x](https://npmx.dev/package/eslint-plugin-react-x) and [eslint-plugin-react-dom](https://npmx.dev/package/eslint-plugin-react-dom) for React-specific lint rules:

```js
// eslint.config.js
import reactX from 'eslint-plugin-react-x'
import reactDom from 'eslint-plugin-react-dom'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...
      // Enable lint rules for React
      reactX.configs['recommended-typescript'],
      // Enable lint rules for React DOM
      reactDom.configs.recommended,
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])

```
