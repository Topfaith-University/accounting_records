import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterModule } from '@angular/router';
import { PayablesService } from '../../services/payables.service';

@Component({
  selector: 'app-vendor-statement',
  standalone: true,
  imports: [CommonModule, RouterModule],
  templateUrl: './vendor-statement.component.html',
})
export class VendorStatementComponent implements OnInit {
  statement: any = null;
  loading = true;
  error = '';

  private id = '';

  constructor(private route: ActivatedRoute, private payables: PayablesService) {}

  async ngOnInit() {
    this.id = this.route.snapshot.paramMap.get('id') ?? '';
    try {
      this.statement = await this.payables.getVendorStatement(this.id);
    } catch {
      this.error = 'Failed to load vendor statement.';
    } finally {
      this.loading = false;
    }
  }

  async exportFile(format: 'pdf' | 'xlsx') {
    try {
      await this.payables.exportVendorStatement(this.id, format);
    } catch {
      this.error = 'Export failed.';
    }
  }
}
