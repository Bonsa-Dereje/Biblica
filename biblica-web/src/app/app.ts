import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { API_URL } from './core/api.config';
import { BiblicaService } from './core/biblica.service';
import { SearchBox } from './layout/search-box';
import { Icon } from './shared/icon';

/** The shell: black sidebar, top bar with the search box, and the routed page. */
@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, SearchBox, Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {
  private readonly api = inject(BiblicaService);
  private readonly router = inject(Router);

  protected readonly apiUrl = API_URL;
  protected readonly randomLoading = signal(false);

  protected openRandom(): void {
    if (this.randomLoading()) return;
    this.randomLoading.set(true);
    this.api.random().subscribe({
      next: ({ chapter }) => {
        this.randomLoading.set(false);
        this.router.navigate(['/read', chapter.id]);
      },
      error: () => this.randomLoading.set(false),
    });
  }
}
