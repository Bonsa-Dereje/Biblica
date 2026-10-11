import { Routes } from '@angular/router';

// Each page is lazy-loaded: its code is only downloaded when you first visit it.
// Route params (:order, :id) and query params (?q=) arrive as component inputs
// thanks to withComponentInputBinding() in app.config.ts.
export const routes: Routes = [
  { path: '', title: 'Biblica', loadComponent: () => import('./pages/dashboard/dashboard').then((m) => m.Dashboard) },
  { path: 'books', title: 'Books · Biblica', loadComponent: () => import('./pages/books/books').then((m) => m.Books) },
  { path: 'book/:order', title: 'Book · Biblica', loadComponent: () => import('./pages/book/book').then((m) => m.BookPage) },
  { path: 'search', title: 'Search · Biblica', loadComponent: () => import('./pages/search/search').then((m) => m.SearchPage) },
  { path: 'read/:id', title: 'Reader · Biblica', loadComponent: () => import('./pages/reader/reader').then((m) => m.Reader) },
  { path: '**', redirectTo: '' },
];
