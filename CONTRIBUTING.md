# Contributing to Lumenis AI

First off, thank you for considering contributing to Lumenis AI! We aim to build the cleanest, most minimalist, and highly accurate SaaS platform for medical imaging analysis.

## 🤝 How Can I Contribute?

### 1. Reporting Bugs
If you find a bug, please open an issue in the repository. Provide as much detail as possible:
- Steps to reproduce the bug.
- Expected behavior vs. actual behavior.
- Error logs or screenshots.

### 2. Suggesting Enhancements
We are always looking to improve our UI/UX and analytical accuracy. Open an issue with the `enhancement` label and detail your proposal.

### 3. Submitting Pull Requests
If you are ready to write code, please follow this process:
1. Fork the repository and create your feature branch: `git checkout -b feature/my-new-feature`
2. Commit your changes following the [Commit Guidelines](#-commit-guidelines).
3. Ensure all CI/CD checks pass locally.
4. Push to the branch: `git push origin feature/my-new-feature`
5. Submit a Pull Request.

---

## 💻 Development Workflow

We use Docker to ensure consistent development environments.

1. **Start the Stack**: 
   ```bash
   make dev
   ```
2. **Backend Development**: 
   The FastAPI app is volume-mounted. Any changes in `backend/app/` will auto-reload the server.
3. **Frontend Development**: 
   Because the Next.js frontend is built into an optimized standalone container, you will need to restart the container for heavy UI updates, or run it locally outside of docker using `npm run dev` in the `/frontend` directory.

---

## 📐 Coding Standards

### Python (Backend)
- **Formatting**: We use `ruff` for extremely fast linting and formatting. 
- **Types**: All functions must have strict type hints.
- **Async**: Use `async`/`await` for all DB interactions (`asyncpg`) and external API calls.

### JavaScript/React (Frontend)
- **Aesthetic**: Strictly adhere to the monochrome, sharp-edged minimalist design system in `globals.css`. 
- **NO Tailwind**: We use Vanilla CSS and CSS Modules to enforce rigid structural control.
- **Client vs Server**: Use React Server Components by default. Only use `'use client'` when state (`useState`) or interactivity is strictly required.

---

## 📝 Commit Guidelines

Please use semantic commit messages:
- `feat: add longitudinal scan comparisons`
- `fix: resolve websocket streaming timeout`
- `docs: update setup instructions in README`
- `style: enforce 0px border-radius on buttons`
- `refactor: modularize the job fetching API`

Thank you for helping us make Lumenis AI better!
